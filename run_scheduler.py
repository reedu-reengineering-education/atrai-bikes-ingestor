"""
Periodic sync scheduler.

Runs the archive ingestion job on a fixed interval.
Configure with SYNC_INTERVAL_HOURS (default: 6).
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


def run_once() -> None:
    from src.scheduler import sync_sensor_data_job
    result = sync_sensor_data_job()
    if not result.get("success"):
        logger.error(f"Sync failed: {result.get('error')}")


if __name__ == "__main__":
    logger.info(f"Scheduler started — syncing every {INTERVAL_HOURS}h")
    while True:
        logger.info("Starting sync job")
        try:
            run_once()
        except Exception:
            logger.exception("Sync job raised an exception")
        logger.info(f"Next sync in {INTERVAL_HOURS}h")
        time.sleep(INTERVAL_HOURS * 3600)
