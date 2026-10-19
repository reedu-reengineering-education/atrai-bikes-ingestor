"""
Periodic sync scheduler.

Runs the archive ingestion job (sync, track processing, analysis) on a fixed
interval. Configure with SYNC_INTERVAL_HOURS (default: 6).

    python run_scheduler.py          # run forever
    python run_scheduler.py --once   # run a single job and exit (used by POST /sync)
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

INTERVAL_HOURS = float(os.getenv("SYNC_INTERVAL_HOURS", "6"))


def run_once() -> bool:
    """Run one sync job unless another one (scheduler or API) is running."""
    from src.job_lock import SYNC_LOCK_KEY, job_lock
    from src.scheduler import sync_sensor_data_job

    with job_lock(os.environ["DATABASE_URL"], SYNC_LOCK_KEY) as acquired:
        if not acquired:
            logger.warning("Another sync job is already running, skipping")
            return True
        result = sync_sensor_data_job()
    if not result.get("success"):
        logger.error(f"Sync failed: {result.get('error')}")
    return bool(result.get("success"))


if __name__ == "__main__":
    if "--once" in sys.argv[1:]:
        try:
            sys.exit(0 if run_once() else 1)
        except Exception:
            logger.exception("Sync job raised an exception")
            sys.exit(1)

    logger.info(f"Scheduler started — syncing every {INTERVAL_HOURS}h")
    while True:
        logger.info("Starting sync job")
        try:
            run_once()
        except Exception:
            logger.exception("Sync job raised an exception")
        logger.info(f"Next sync in {INTERVAL_HOURS}h")
        time.sleep(INTERVAL_HOURS * 3600)
