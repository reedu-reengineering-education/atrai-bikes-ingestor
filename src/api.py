"""
Atrai Bikes API

Single service that handles:
  - Campaign statistics (GET /campaigns)
  - Data ingestion from the OpenSenseMap archive (POST /sync)
  - Analysis pipeline: bumpy roads, overtaking distance, etc. (POST /analyze)
  - Collection browsing: inspect analysis result tables (GET /collections)
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# Ensure src/ is in sys.path so analysis processes can resolve
# `from config.db_config import DatabaseConfig` as a top-level import.
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Derive DATABASE_HOST / PORT / NAME / USER / PASSWORD from DATABASE_URL so
# the analysis processes (which use the individual env vars) work without
# requiring the user to set them separately.
# ---------------------------------------------------------------------------
def _sync_db_env_from_url() -> None:
    url = os.getenv("DATABASE_URL")
    if url and not os.getenv("DATABASE_HOST"):
        p = urlparse(url)
        os.environ.setdefault("DATABASE_HOST", p.hostname or "localhost")
        os.environ.setdefault("DATABASE_PORT", str(p.port or 5432))
        os.environ.setdefault("DATABASE_NAME", p.path.lstrip("/"))
        os.environ.setdefault("DATABASE_USER", p.username or "postgres")
        os.environ.setdefault("DATABASE_PASSWORD", p.password or "")


_sync_db_env_from_url()

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Atrai Bikes API",
    description="Ingestion, analysis and statistics for atrai bike campaign data",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


# ---------------------------------------------------------------------------
# In-memory status stores (non-persistent, good enough for single-process)
# ---------------------------------------------------------------------------
_sync_lock = threading.Lock()
_sync_status: dict = {"running": False, "last_run": None, "result": None}

_analyze_status: dict = {}  # campaign -> status dict


# ===========================================================================
# Existing campaign stats endpoints
# ===========================================================================
class CampaignStats(BaseModel):
    grouptag: Optional[str] = None
    total_tracks: int
    total_distance_km: float
    total_duration_hours: float
    avg_track_distance_km: float
    avg_track_duration_minutes: float
    avg_speed_kmh: float
    max_track_distance_km: float
    num_riders: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class AllCampaignsStats(BaseModel):
    campaigns: list[CampaignStats]
    total_tracks: int
    total_distance_km: float


# groupTags is stored as a JSON array string: ["bike", "atrai", "heilbronn"]
# Use jsonb containment to check membership: "groupTags"::jsonb ? %s
_CAMPAIGN_QUERY = """
SELECT
    %s                                                     AS grouptag,
    COUNT(DISTINCT id)                                     AS total_tracks,
    COALESCE(SUM(distance_meters),  0) / 1000             AS total_distance_km,
    COALESCE(SUM(duration_seconds), 0) / 3600             AS total_duration_hours,
    COALESCE(AVG(distance_meters),  0) / 1000             AS avg_track_distance_km,
    COALESCE(AVG(duration_seconds), 0) / 60               AS avg_track_duration_minutes,
    CASE WHEN SUM(duration_seconds) > 0
         THEN (SUM(distance_meters) / SUM(duration_seconds)) * 3.6
         ELSE 0 END                                        AS avg_speed_kmh,
    COALESCE(MAX(distance_meters),  0) / 1000             AS max_track_distance_km,
    COUNT(DISTINCT "boxId")                               AS num_riders,
    MIN("startTime")::text                                AS start_date,
    MAX("endTime")::text                                  AS end_date
FROM tracks
WHERE "groupTags"::jsonb ? %s
"""

# Same aggregates for all grouptags in a single scan of tracks.
_ALL_CAMPAIGNS_QUERY = """
SELECT
    g.tag                                                  AS grouptag,
    COUNT(DISTINCT t.id)                                   AS total_tracks,
    COALESCE(SUM(t.distance_meters),  0) / 1000           AS total_distance_km,
    COALESCE(SUM(t.duration_seconds), 0) / 3600           AS total_duration_hours,
    COALESCE(AVG(t.distance_meters),  0) / 1000           AS avg_track_distance_km,
    COALESCE(AVG(t.duration_seconds), 0) / 60             AS avg_track_duration_minutes,
    CASE WHEN SUM(t.duration_seconds) > 0
         THEN (SUM(t.distance_meters) / SUM(t.duration_seconds)) * 3.6
         ELSE 0 END                                        AS avg_speed_kmh,
    COALESCE(MAX(t.distance_meters),  0) / 1000           AS max_track_distance_km,
    COUNT(DISTINCT t."boxId")                             AS num_riders,
    MIN(t."startTime")::text                              AS start_date,
    MAX(t."endTime")::text                                AS end_date
FROM tracks t
CROSS JOIN LATERAL jsonb_array_elements_text(
    CASE WHEN jsonb_typeof(t."groupTags"::jsonb) = 'array' THEN t."groupTags"::jsonb END
) AS g(tag)
WHERE g.tag = ANY(%s)
GROUP BY g.tag
"""


def _row_to_stats(row: dict) -> CampaignStats:
    return CampaignStats(
        grouptag=row["grouptag"],
        total_tracks=row["total_tracks"],
        total_distance_km=float(row["total_distance_km"]),
        total_duration_hours=float(row["total_duration_hours"]),
        avg_track_distance_km=float(row["avg_track_distance_km"]),
        avg_track_duration_minutes=float(row["avg_track_duration_minutes"]),
        avg_speed_kmh=float(row["avg_speed_kmh"]),
        max_track_distance_km=float(row["max_track_distance_km"]),
        num_riders=row["num_riders"],
        start_date=row["start_date"],
        end_date=row["end_date"],
    )


@app.get("/campaigns", response_model=AllCampaignsStats)
def get_all_campaigns():
    """Aggregated statistics for all configured campaigns (from GROUPTAGS env var)."""
    grouptags_env = os.getenv("GROUPTAGS", "")
    grouptags = [t.strip() for t in grouptags_env.split(",") if t.strip()]
    try:
        conn = get_db()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(_ALL_CAMPAIGNS_QUERY, (grouptags,))
                rows = {r["grouptag"]: r for r in cur.fetchall()}
        finally:
            conn.close()
        # Keep the order of GROUPTAGS in the response
        campaigns = [
            _row_to_stats(rows[t]) for t in grouptags
            if t in rows and rows[t]["total_tracks"] > 0
        ]
        return AllCampaignsStats(
            campaigns=campaigns,
            total_tracks=sum(c.total_tracks for c in campaigns),
            total_distance_km=sum(c.total_distance_km for c in campaigns),
        )
    except Exception as e:
        logger.error(f"get_all_campaigns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/campaigns/{grouptag}", response_model=CampaignStats)
def get_campaign_stats(grouptag: str):
    """Statistics for a specific campaign (grouptag)."""
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_CAMPAIGN_QUERY, (grouptag, grouptag))
            row = cur.fetchone()
        conn.close()
        if not row or row["total_tracks"] == 0:
            raise HTTPException(status_code=404, detail=f"Campaign '{grouptag}' not found")
        return _row_to_stats(row)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_campaign_stats({grouptag}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# POST /sync  — ingest new data from the OpenSenseMap archive
# ===========================================================================
@app.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    """
    Trigger a full data sync from the OpenSenseMap archive.

    The sync runs in the background. Poll **GET /sync/status** for progress.
    """
    with _sync_lock:
        if _sync_status["running"]:
            return {"status": "already_running", "started_at": _sync_status["last_run"]}
        _sync_status["running"] = True
        _sync_status["last_run"] = datetime.now(timezone.utc).isoformat()
        _sync_status["result"] = None

    background_tasks.add_task(_run_sync)
    return {"status": "started", "started_at": _sync_status["last_run"]}


@app.get("/sync/status")
async def sync_status():
    """Current / last sync job status."""
    return _sync_status


def _run_sync() -> None:
    try:
        from src.scheduler import sync_sensor_data_job

        result = sync_sensor_data_job()
        _sync_status["result"] = result
    except Exception as e:
        logger.exception("Sync job failed")
        _sync_status["result"] = {"success": False, "error": str(e)}
    finally:
        _sync_status["running"] = False


# ===========================================================================
# POST /analyze  — run analysis processes for one or more campaigns
# ===========================================================================
AVAILABLE_PROCESSES = [
    "road_network",
    "bumpy_roads",
    "dangerous_places",
    "distances",
    "speed_traffic_flow",
    "statistics",
]


class AnalyzeRequest(BaseModel):
    campaigns: list[str]
    processes: list[str] | str = "all"


@app.post("/analyze")
async def trigger_analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Run analysis processes (bumpy roads, overtaking distance, speed/traffic flow …)
    for one or more campaigns.

    `campaigns` — list of grouptag strings, e.g. `["heilbronn"]`  
    `processes` — `"all"` or a subset of:
    `road_network`, `bumpy_roads`, `dangerous_places`, `distances`,
    `speed_traffic_flow`, `statistics`

    Results are written to the database. Poll **GET /analyze/status** for progress.
    """
    procs: list[str]
    if request.processes == "all":
        procs = AVAILABLE_PROCESSES
    elif isinstance(request.processes, list):
        invalid = set(request.processes) - set(AVAILABLE_PROCESSES)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown processes: {sorted(invalid)}. Valid: {AVAILABLE_PROCESSES}",
            )
        procs = request.processes
    else:
        raise HTTPException(status_code=422, detail="'processes' must be 'all' or a list")

    for campaign in request.campaigns:
        _analyze_status[campaign] = {
            "running": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "processes": procs,
            "completed": [],
            "failed": [],
        }

    background_tasks.add_task(_run_analyze, request.campaigns, procs)
    return {"status": "started", "campaigns": request.campaigns, "processes": procs}


@app.get("/analyze/status")
async def analyze_status():
    """Status of the last analyze job per campaign."""
    return _analyze_status


def _run_analyze(campaigns: list[str], processes: list[str]) -> None:
    import yaml

    token = os.getenv("INT_API_TOKEN", "")
    campaigns_config_path = os.getenv("CAMPAIGNS_CONFIG", "./campaigns.yml")
    try:
        with open(campaigns_config_path) as f:
            campaigns_cfg = yaml.safe_load(f).get("campaigns", {})
    except Exception:
        campaigns_cfg = {}

    for campaign in campaigns:
        for proc_name in processes:
            try:
                _call_process(proc_name, campaign, token, campaigns_cfg)
                _analyze_status[campaign]["completed"].append(proc_name)
                logger.info(f"[analyze] '{proc_name}' for '{campaign}' done")
            except Exception as e:
                _analyze_status[campaign]["failed"].append(proc_name)
                logger.warning(
                    f"[analyze] '{proc_name}' for '{campaign}' failed: "
                    f"{type(e).__name__}: {e}",
                    exc_info=True,
                )

        _analyze_status[campaign]["running"] = False
        _analyze_status[campaign]["finished_at"] = datetime.now(timezone.utc).isoformat()


def _call_process(proc_name: str, campaign: str, token: str, campaigns_cfg: dict) -> None:
    """Instantiate and execute an analysis process class directly."""
    # col_create=False: skip writing to pygeoapi config.yml
    base_inputs = {"campaign": campaign, "token": token, "col_create": False}

    if proc_name == "road_network":
        from src.atrai_processes.road_network import RoadNetwork

        location = campaigns_cfg.get(campaign, {}).get(
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


# ===========================================================================
# GET /collections  — list analysis result tables in the database
# ===========================================================================
# Patterns that identify analysis result tables written by the processes
_ANALYSIS_TABLE_PREFIXES = (
    "bumpy_roads_",
    "danger_zones_",
    "danger_zones_PM_",
    "overtaking_distance_",
    "road_network_",
    "bike_road_network_",
    "speed_map_",
    "traffic_flow_",
    "speed_traffic_flow_",
    "statistics",
    "tracks",
    "track_points",
    "osem_bike_data",
    "osem_home_data_heilbronn",
)


def _list_analysis_tables() -> list[str]:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        all_tables = [r[0] for r in cur.fetchall()]
    conn.close()
    return [
        t for t in all_tables
        if any(t.startswith(prefix) or t == prefix.rstrip("_") for prefix in _ANALYSIS_TABLE_PREFIXES)
    ]


@app.get("/collections")
def list_collections():
    """List all analysis result tables that exist in the database."""
    try:
        tables = _list_analysis_tables()
        return {"collections": tables}
    except Exception as e:
        logger.error(f"list_collections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Rows fetched per round trip when streaming collection items
_ITEMS_BATCH_SIZE = 2000


@app.get("/collections/{name}/items")
def get_collection_items(
    name: str,
    limit: int = Query(100, ge=0),
    offset: int = Query(0, ge=0),
    campaign: Optional[str] = None,
):
    """
    Return features from an analysis result table as GeoJSON.

    - `limit` — max rows to return (default 100, use 0 for unlimited — careful with large tables)
    - `offset` — skip this many rows (for pagination)
    - `campaign` — unused filter placeholder (future use)

    Features are serialised to GeoJSON by PostGIS and streamed in batches, so
    large limits neither build the whole response in Python nor hold it in memory.

    For raw sensor data and tracks, use the Martin tile server (:3000) instead.
    """
    # Validate table name against known tables to prevent SQL injection
    try:
        known = _list_analysis_tables()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if name not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Collection '{name}' not found. Available: {known}",
        )

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Find the geometry column
            cur.execute(
                """
                SELECT column_name, udt_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name   = %s
                  AND udt_name     IN ('geometry','geography')
                ORDER BY ordinal_position
                LIMIT 1
                """,
                (name,),
            )
            geom_row = cur.fetchone()

            # Total row count for pagination
            cur.execute(f'SELECT COUNT(*) FROM "{name}"')
            total = cur.fetchone()[0]

        # One GeoJSON Feature (as text) per row. Postgres renders timestamps as
        # ISO 8601 and non-finite floats as strings, so the output is valid JSON.
        if geom_row and geom_row[1] == "geometry":
            feature_sql = "ST_AsGeoJSON(t.*, %s)"
            params: tuple = (geom_row[0],)
        elif geom_row:
            # The record form of ST_AsGeoJSON only picks up geometry columns
            feature_sql = (
                "json_build_object('type', 'Feature',"
                f""" 'geometry', ST_AsGeoJSON(t."{geom_row[0]}")::json,"""
                " 'properties', to_jsonb(t) - %s)::text"
            )
            params = (geom_row[0],)
        else:
            feature_sql = (
                "json_build_object('type', 'Feature', 'geometry', NULL,"
                " 'properties', to_json(t))::text"
            )
            params = ()

        limit_sql = f"LIMIT {limit}" if limit > 0 else ""
        query = f'SELECT {feature_sql} FROM (SELECT * FROM "{name}" {limit_sql} OFFSET %s) t'

        # Server-side cursor: rows arrive in batches instead of all at once.
        # Fetch the first batch here so query errors still become a 500.
        cur = conn.cursor(name="collection_items")
        cur.execute(query, params + (offset,))
        first_batch = cur.fetchmany(_ITEMS_BATCH_SIZE)
    except Exception as e:
        conn.close()
        logger.error(f"get_collection_items({name}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    def stream():
        returned = 0
        # The opening is sent together with the first batch: Caddy's `encode`
        # only compresses a response without Content-Length if its first
        # chunk exceeds minimum_length (512 bytes).
        chunk = (
            '{"type":"FeatureCollection",'
            f'"numberMatched":{total},"offset":{offset},"limit":{limit},'
            '"features":['
        )
        try:
            batch = first_batch
            while batch:
                chunk += ("," if returned else "") + ",".join(row[0] for row in batch)
                yield chunk
                chunk = ""
                returned += len(batch)
                batch = cur.fetchmany(_ITEMS_BATCH_SIZE)
            yield chunk + f'],"numberReturned":{returned}}}'
        except Exception:
            # Headers are already sent; all we can do is log and cut the stream
            logger.exception(f"get_collection_items({name}): streaming failed")
            raise
        finally:
            conn.close()

    return StreamingResponse(stream(), media_type="application/json")


# ===========================================================================
# Health
# ===========================================================================
@app.get("/health")
async def health_check():
    return {"status": "ok"}
