"""
Scheduler Module

This module provides the main sync job execution.
It can be executed as a standalone Python script or scheduled via cron.

The script:
1. Loads environment configuration (DATABASE_URL, LOG_LEVEL)
2. Initializes all sync components (API client, parser, database, coordinator)
3. Runs the complete synchronization job
4. Handles errors and logs execution details

Requirements: 7.1, 7.2, 7.3, 7.4
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from dotenv import load_dotenv


logger = logging.getLogger(__name__)


def sync_sensor_data_job() -> Dict[str, Any]:
    """
    Main job function for sensor data synchronization.
    
    This function is the entry point for the sync job. It instantiates all
    required components (API client, parser, database manager, and sync
    coordinator) and runs the complete synchronization job.
    
    The function implements comprehensive error handling and logging to ensure
    that job failures are properly reported and can be debugged.
    
    Returns:
        Dictionary with job execution results:
        - success: Boolean indicating if job completed successfully
        - start_time: ISO timestamp when job started
        - end_time: ISO timestamp when job ended
        - duration_seconds: Job execution duration
        - error: Error message (if failed)
    
    Raises:
        Exception: Re-raises any exception after logging
    
    Requirements: 7.3, 7.4
    """
    start_time = datetime.now(timezone.utc)
    result = {
        "success": False,
        "start_time": start_time.isoformat(),
        "end_time": None,
        "duration_seconds": None,
        "error": None,
    }
    
    logger.info("=" * 80)
    logger.info(f"Starting scheduled sync job at {start_time.isoformat()}")
    logger.info("=" * 80)
    
    # Initialize component references for cleanup
    api_client = None
    database = None
    
    try:
        # Load environment variables (Requirement 7.1)
        load_dotenv()
        
        # Validate required configuration
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        
        # Parse grouptags from environment (comma-separated)
        grouptags_env = os.getenv("GROUPTAGS", "atrai")
        grouptags = [tag.strip() for tag in grouptags_env.split(",") if tag.strip()]
        if not grouptags:
            grouptags = ["atrai"]
        
        # Parse default start date from environment
        from datetime import date as date_type
        default_start_date_str = os.getenv("DEFAULT_START_DATE", "2024-01-01")
        try:
            default_start_date = date_type.fromisoformat(default_start_date_str)
        except ValueError:
            logger.warning(f"Invalid DEFAULT_START_DATE '{default_start_date_str}', using 2024-01-01")
            default_start_date = date_type(2024, 1, 1)
        
        logger.info(f"Environment configuration loaded successfully")
        logger.info(f"Grouptags to sync: {grouptags}")
        logger.info(f"Default start date: {default_start_date}")
        
        # Import components (import here to avoid circular dependencies)
        from src.api_client import OpenSenseMapClient
        from src.parser import DataParser
        from src.database import DatabaseManager
        from src.sync_coordinator import SyncCoordinator
        
        # Initialize components (Requirement 7.3)
        logger.info("Initializing sync components...")
        api_client = OpenSenseMapClient()
        parser = DataParser()
        database = DatabaseManager(database_url)
        
        # Create database schema if it doesn't exist
        logger.info("Creating database schema (if not exists)...")
        database.create_schema()
        logger.info("Database schema ready")
        
        coordinator = SyncCoordinator(
            api_client, parser, database,
            grouptags=grouptags,
            default_start_date=default_start_date
        )
        logger.info("Components initialized successfully")
        
        # Run sync job (Requirement 7.3)
        logger.info("Starting synchronization process...")
        coordinator.run_sync_job()
        logger.info("Synchronization process completed")
        
        # Run track processing
        logger.info("Starting track processing...")
        from src.track_processor import TrackProcessor
        track_processor = TrackProcessor(database_url)
        tracks_stored = track_processor.process()
        logger.info(f"Track processing completed. Stored {tracks_stored} tracks")

        # Trigger analysis pipeline via pygeoapi for each synced grouptag
        pygeoapi_url = os.getenv("PYGEOAPI_URL", "")
        int_api_token = os.getenv("INT_API_TOKEN", "")
        if pygeoapi_url and int_api_token:
            import requests as req
            logger.info(f"Triggering analysis pipeline for grouptags: {grouptags}")
            for grouptag in grouptags:
                try:
                    resp = req.post(
                        f"{pygeoapi_url}/processes/data_ingestion/execution?f=json",
                        json={
                            "inputs": {
                                "token": int_api_token,
                                "campaigns": [grouptag],
                                "processes": "all",
                            }
                        },
                        timeout=7200,
                    )
                    resp.raise_for_status()
                    logger.info(f"Analysis pipeline triggered for grouptag '{grouptag}'")
                except Exception as e:
                    logger.warning(
                        f"Failed to trigger analysis for grouptag '{grouptag}': {e}"
                    )
        else:
            logger.info(
                "PYGEOAPI_URL or INT_API_TOKEN not set — skipping analysis trigger"
            )

        # Calculate execution time
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        # Update result with success information
        result.update({
            "success": True,
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
        })
        
        logger.info("=" * 80)
        logger.info(f"Scheduled sync job completed successfully")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 80)
        
        return result
        
    except Exception as e:
        # Error handling and logging (Requirement 7.4)
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        error_message = str(e)
        
        result.update({
            "success": False,
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "error": error_message,
        })
        
        logger.error("=" * 80)
        logger.error(f"Scheduled sync job failed after {duration:.2f} seconds")
        logger.error(f"Error: {error_message}")
        logger.error("=" * 80)
        logger.exception("Full exception details:")
        
        # Re-raise exception (Requirement 7.4)
        raise
        
    finally:
        # Clean up resources (Requirement 7.4)
        logger.info("Cleaning up resources...")
        try:
            if api_client is not None:
                api_client.close()
                logger.debug("API client closed")
        except Exception as e:
            logger.warning(f"Error closing API client: {e}")
        
        try:
            if database is not None:
                database.close()
                logger.debug("Database connection closed")
        except Exception as e:
            logger.warning(f"Error closing database connection: {e}")
        
        logger.info("Resource cleanup completed")


def run_scheduled_sync():
    """
    Legacy entry point for scheduled sync jobs.
    
    This function maintains backward compatibility and provides a simple
    interface for running the sync job. It wraps sync_sensor_data_job()
    and handles the result.
    """
    try:
        result = sync_sensor_data_job()
        if result["success"]:
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    # Configure logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Run the sync job
    run_scheduled_sync()
