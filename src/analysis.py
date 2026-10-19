"""
Analysis pipeline runner.

Each (campaign, process) pair runs in its own Python subprocess, one at a time:

- memory is fully returned to the OS after every process (pandas/geopandas
  keep a lot of it otherwise),
- a process that crashes, is OOM-killed or exceeds ANALYSIS_TIMEOUT_SECONDS
  fails on its own without taking the API or scheduler down,
- a Postgres advisory lock keeps the API and the scheduler from running
  analyses at the same time.

Run a single process directly with:
    python -m src.analysis <campaign> <process>
"""

import logging
import os
import subprocess
import sys
from typing import Callable, Optional
from urllib.parse import urlparse

import psycopg2
import yaml

from src.job_lock import ANALYSIS_LOCK_KEY, job_lock

logger = logging.getLogger(__name__)

AVAILABLE_PROCESSES = [
    "road_network",
    "bumpy_roads",
    "dangerous_places",
    "distances",
    "speed_traffic_flow",
    "statistics",
]

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")


def prepare_process_env() -> None:
    """
    Set up what the analysis processes expect.

    They import `config.db_config` as a top-level package (so src/ must be on
    sys.path) and read DATABASE_HOST / PORT / NAME / USER / PASSWORD, which are
    derived here from DATABASE_URL unless set explicitly.
    """
    if _SRC_DIR not in sys.path:
        sys.path.insert(0, _SRC_DIR)

    url = os.getenv("DATABASE_URL")
    if url and not os.getenv("DATABASE_HOST"):
        p = urlparse(url)
        os.environ.setdefault("DATABASE_HOST", p.hostname or "localhost")
        os.environ.setdefault("DATABASE_PORT", str(p.port or 5432))
        os.environ.setdefault("DATABASE_NAME", p.path.lstrip("/"))
        os.environ.setdefault("DATABASE_USER", p.username or "postgres")
        os.environ.setdefault("DATABASE_PASSWORD", p.password or "")


def load_campaigns_config() -> dict:
    path = os.getenv("CAMPAIGNS_CONFIG", "./campaigns.yml")
    try:
        with open(path) as f:
            return (yaml.safe_load(f) or {}).get("campaigns", {}) or {}
    except Exception as e:
        logger.warning(f"Could not load campaigns config from {path}: {e}")
        return {}


def run_process(proc_name: str, campaign: str) -> None:
    """Instantiate and execute one analysis process in the current process."""
    prepare_process_env()
    # The processes compare this against INT_API_TOKEN (default 'token')
    token = os.environ.get("INT_API_TOKEN", "token")
    # col_create=False: skip writing to pygeoapi config.yml
    base_inputs = {"campaign": campaign, "token": token, "col_create": False}

    if proc_name == "road_network":
        from src.atrai_processes.road_network import RoadNetwork

        location = load_campaigns_config().get(campaign, {}).get(
            "road_network", [{"city": campaign, "country": "Germany"}]
        )
        RoadNetwork({"name": "road_network"}).execute({**base_inputs, "location": location})

    elif proc_name == "bumpy_roads":
        from src.atrai_processes.bumpy_roads import BumpyRoads

        BumpyRoads({"name": "bumpy_roads"}).execute(base_inputs)

    elif proc_name == "dangerous_places":
        from src.atrai_processes.dangerous_places import DangerousPlaces

        DangerousPlaces({"name": "dangerous_places"}).execute(base_inputs)

    elif proc_name == "distances":
        from src.atrai_processes.distances_flowmap import Distances

        Distances({"name": "distances"}).execute(base_inputs)

    elif proc_name == "speed_traffic_flow":
        from src.atrai_processes.speed_traffic_flow import SpeedTrafficFlow

        SpeedTrafficFlow({"name": "speed_traffic_flow"}).execute(base_inputs)

    elif proc_name == "statistics":
        from src.atrai_processes.statistics import Statistics

        Statistics({"name": "statistics"}).execute(base_inputs)

    else:
        raise ValueError(f"Unknown process: {proc_name}")


def _road_network_exists(database_url: str, campaign: str) -> bool:
    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f'public."bike_road_network_{campaign}"',))
            return cur.fetchone()[0]
    finally:
        conn.close()


def _run_in_subprocess(proc_name: str, campaign: str, timeout: int) -> tuple[bool, str]:
    """Run one process via `python -m src.analysis`. Returns (ok, detail)."""
    cmd = [sys.executable, "-m", "src.analysis", campaign, proc_name]
    try:
        # stdout/stderr are inherited, so the process logs end up in the container log
        result = subprocess.run(cmd, cwd=_PROJECT_ROOT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    if result.returncode == 0:
        return True, "done"
    if result.returncode < 0:
        # e.g. -9: killed by SIGKILL, typically the OOM killer
        return False, f"killed by signal {-result.returncode} (out of memory?)"
    return False, f"exit code {result.returncode}"


def run_analysis(
    campaigns: list[str],
    processes: list[str],
    refresh_road_network: bool = True,
    on_result: Optional[Callable[[str, str, str], None]] = None,
) -> bool:
    """
    Run `processes` for each campaign, one subprocess at a time.

    refresh_road_network=False skips `road_network` for campaigns whose road
    network table already exists. Downloading it from OpenStreetMap is slow,
    memory-hungry (São Paulo alone needs several GB) and the network rarely
    changes, so the scheduler only imports missing ones.

    on_result(campaign, process, outcome) is called after each process with
    outcome "completed", "failed" or "skipped".

    Returns False without running anything if another analysis holds the lock.
    """
    database_url = os.environ["DATABASE_URL"]
    timeout = int(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "3600"))

    with job_lock(database_url, ANALYSIS_LOCK_KEY) as acquired:
        if not acquired:
            logger.warning("[analyze] another analysis is already running, skipping")
            return False

        for campaign in campaigns:
            for proc_name in processes:
                if (
                    proc_name == "road_network"
                    and not refresh_road_network
                    and _road_network_exists(database_url, campaign)
                ):
                    logger.info(f"[analyze] road network for '{campaign}' exists, skipping import")
                    outcome = "skipped"
                else:
                    logger.info(f"[analyze] '{proc_name}' for '{campaign}' started")
                    ok, detail = _run_in_subprocess(proc_name, campaign, timeout)
                    outcome = "completed" if ok else "failed"
                    log = logger.info if ok else logger.error
                    log(f"[analyze] '{proc_name}' for '{campaign}': {detail}")
                if on_result:
                    on_result(campaign, proc_name, outcome)
    return True


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    if len(sys.argv) != 3 or sys.argv[2] not in AVAILABLE_PROCESSES:
        print(f"usage: python -m src.analysis <campaign> <{'|'.join(AVAILABLE_PROCESSES)}>")
        sys.exit(2)
    try:
        run_process(sys.argv[2], sys.argv[1])
    except Exception:
        logger.exception(f"[analyze] '{sys.argv[2]}' for '{sys.argv[1]}' failed")
        sys.exit(1)
