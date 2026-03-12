"""
Sync Coordinator

This module orchestrates the synchronization workflow, coordinating between
the API client, parser, and database manager to fetch and store sensor data.
"""

from datetime import date, timedelta
from typing import Optional
import logging
import json

from .parser import Measurement


logger = logging.getLogger(__name__)


class SyncCoordinator:
    """Orchestrates the synchronization workflow."""
    
    def __init__(self, api_client, parser, database, grouptags: list[str] = None, default_start_date: date = None):
        """
        Initialize with dependencies.
        
        Args:
            api_client: OpenSenseMapClient instance
            parser: DataParser instance
            database: DatabaseManager instance
            grouptags: List of grouptags to sync (default: ["atrai"])
            default_start_date: Default start date for boxes with no sync history (default: 2024-01-01)
        """
        self.api_client = api_client
        self.parser = parser
        self.database = database
        self.grouptags = grouptags if grouptags else ["atrai"]
        self.default_start_date = default_start_date if default_start_date else date(2024, 1, 1)
    
    def run_sync_job(self):
        """
        Execute a complete sync job.
        
        Fetches all boxes for each configured grouptag and syncs data for each box
        from their last sync date to the current date.
        
        Requirements: 1.1, 5.1, 8.1
        """
        logger.info("Starting sync job")
        logger.info(f"Configured grouptags: {self.grouptags}")
        
        total_boxes = 0
        
        try:
            for grouptag in self.grouptags:
                # Fetch all boxes with this grouptag (Requirement 1.1)
                logger.info(f"Fetching boxes with grouptag '{grouptag}'")
                boxes = self.api_client.fetch_boxes(grouptag)
                logger.info(f"Found {len(boxes)} boxes for grouptag '{grouptag}'")
                
                # Iterate through boxes and sync each one (Requirement 5.1, 8.1)
                for i, box in enumerate(boxes, 1):
                    try:
                        logger.info(f"[{grouptag}] [{i}/{len(boxes)}] Syncing box: {box.name} ({box.id})")
                        self.sync_box(box)
                        logger.info(f"[{grouptag}] [{i}/{len(boxes)}] Successfully synced {box.name}")
                    except Exception as e:
                        # Handle exceptions gracefully - log error and continue with next box
                        logger.error(f"[{grouptag}] [{i}/{len(boxes)}] Error syncing box {box.name} ({box.id}): {e}", exc_info=True)
                        continue
                
                total_boxes += len(boxes)
            
            logger.info(f"Sync job completed. Processed {total_boxes} boxes across {len(self.grouptags)} grouptag(s)")
            
        except Exception as e:
            # Handle exceptions gracefully at the job level
            logger.error(f"Sync job failed: {e}", exc_info=True)
            raise
    
    def sync_box(self, box, start_date: Optional[date] = None, end_date: Optional[date] = None):
        """
        Sync data for a single box within date range.
        
        Determines the start date by querying the latest sync date from the database,
        or uses the configured default_start_date if no sync history exists. Iterates
        through dates from start date to current date, calling process_day() for each date.
        Updates sync state to today's date after completing the sync run.
        
        Args:
            box: Box object with id, name, sanitized_name, and grouptags
            start_date: Optional start date for sync (inclusive). If None, determined from sync state.
            end_date: Optional end date for sync (inclusive). If None, defaults to today.
        """
        # Determine end date (default to today)
        if end_date is None:
            end_date = date.today()
        
        # Determine start date (Requirement 5.1, 5.2, 5.3)
        if start_date is None:
            # Get latest sync date from database
            latest_sync_date = self.database.get_latest_sync_date(box.id)
            
            if latest_sync_date is None:
                # No sync history, start from default_start_date
                start_date = self.default_start_date
                logger.info(f"No sync history for {box.name} ({box.id}), starting from {start_date}")
            else:
                # Start from day after latest sync date (Requirement 5.3)
                start_date = latest_sync_date + timedelta(days=1)
                logger.info(f"Resuming sync for {box.name} ({box.id}) from {start_date}")
        
        # Iterate through dates from start_date to end_date (Requirement 6.3)
        current_date = start_date
        while current_date <= end_date:
            # Process this day
            self.process_day(box, current_date)
            
            # Move to next day
            current_date += timedelta(days=1)
        
        # Update sync state to today's date after completing the sync run (Requirement 5.4, 8.2)
        # This ensures the next run starts from today, not from the last measurement date
        self.database.update_sync_state(box.id, end_date)
        logger.info(f"Updated sync state for {box.name} to {end_date}")
    
    def process_day(self, box, target_date: date):
        """
        Process data for a single box and date.
        
        Fetches archive metadata and CSV files for the specified box and date,
        parses the data, and stores measurements in the database.
        Handles missing archive data gracefully by logging and continuing.
        
        Args:
            box: Box object with id, name, sanitized_name, and grouptags
            target_date: Date to process
        """
        date_str = target_date.strftime('%Y-%m-%d')
        
        try:
            # Fetch archive metadata for this box and date
            logger.info(f"Processing {box.name} ({box.id}) for date {date_str}")
            logger.info(box.sanitized_name)
            metadata = self.api_client.fetch_archive_metadata(
                box.id, 
                box.sanitized_name, 
                date_str
            )
            
            # Handle missing archive data gracefully (Requirement 2.4, 6.1)
            if metadata is None:
                logger.info(f"No archive data found for {box.name} on {date_str}")
                return
            
            # Parse metadata to get sensor information
            try:
                box_metadata = self.parser.parse_metadata(json.dumps(metadata))
            except ValueError as e:
                logger.error(f"Failed to parse metadata for {box.name} on {date_str}: {e}")
                return
            
            # Fetch and process CSV data for each sensor
            # Group measurements by timestamp to combine multiple phenomena
            measurements_by_timestamp = {}
            
            for sensor in box_metadata.sensors:
                sensor_id = sensor.get('_id')
                sensor_title = sensor.get('title', '')
                
                if not sensor_id:
                    continue
                
                # Map sensor title to database column
                column_name = self.parser.map_sensor_to_column(sensor_title)
                if column_name is None:
                    # Skip sensors we don't track
                    logger.debug(f"Skipping unmapped sensor: {sensor_title}")
                    continue
                
                # Fetch CSV data for this sensor
                csv_content = self.api_client.fetch_archive_csv(
                    box.id,
                    box.sanitized_name,
                    date_str,
                    sensor_id
                )
                
                if csv_content is None:
                    logger.debug(f"No CSV data for sensor {sensor_title} ({sensor_id}) on {date_str}")
                    continue
                
                # Parse CSV data
                try:
                    parsed_data = self.parser.parse_csv(csv_content)
                except Exception as e:
                    logger.error(f"Failed to parse CSV for sensor {sensor_title}: {e}")
                    continue
                
                # Aggregate data points by timestamp
                for data_point in parsed_data:
                    timestamp = data_point['timestamp']
                    
                    # Initialize measurement dict for this timestamp if not exists
                    if timestamp not in measurements_by_timestamp:
                        measurements_by_timestamp[timestamp] = {
                            'boxid': box.id,
                            'boxname': box.name,
                            'grouptags': json.dumps(box.grouptags),
                            'timestamp': timestamp,
                            'longitude': data_point.get('longitude'),
                            'latitude': data_point.get('latitude'),
                        }
                    
                    # Update GPS coordinates if available (use most recent non-null values)
                    if data_point.get('longitude') is not None:
                        measurements_by_timestamp[timestamp]['longitude'] = data_point['longitude']
                    if data_point.get('latitude') is not None:
                        measurements_by_timestamp[timestamp]['latitude'] = data_point['latitude']
                    
                    # Set the sensor value for this phenomenon
                    measurements_by_timestamp[timestamp][column_name] = data_point['value']
            
            # Convert aggregated measurements to Measurement objects
            all_measurements = [
                Measurement(**measurement_data)
                for measurement_data in measurements_by_timestamp.values()
            ]
            
            # Insert measurements into database (using upsert to merge phenomena)
            if all_measurements:
                inserted_count = self.database.insert_measurements(all_measurements)
                logger.info(f"Processed {inserted_count} measurement records for {box.name} on {date_str}")
            else:
                logger.info(f"No measurements to insert for {box.name} on {date_str}")
                
        except Exception as e:
            logger.error(f"Error processing {box.name} on {date_str}: {e}")
