"""
Sync Coordinator

This module orchestrates the synchronization workflow, coordinating between
the API client, parser, and database manager to fetch and store sensor data.
"""

from datetime import date, timedelta
from typing import Optional
import logging
import json

from .parser import Measurement, HomeMeasurement


logger = logging.getLogger(__name__)


class SyncCoordinator:
    """Orchestrates the synchronization workflow."""
    
    def __init__(
        self,
        api_client,
        parser,
        database,
        grouptags: list[str] = None,
        default_start_date: date = None,
        home_grouptag: str = None,
        home_box_ids: list[str] = None,
        home_table: str = "osem_home_data_heilbronn",
    ):
        """
        Initialize with dependencies.

        Args:
            api_client: OpenSenseMapClient instance
            parser: DataParser instance
            database: DatabaseManager instance
            grouptags: List of grouptags to sync (default: ["atrai"])
            default_start_date: Default start date for boxes with no sync history (default: 2024-01-01)
            home_grouptag: Grouptag used to discover senseBox:home stations (e.g. "GreenCityHN").
            home_box_ids: Additional specific box IDs to sync as home devices — for stations
                that aren't tagged with home_grouptag and so can't be discovered that way.
                Merged with the grouptag-discovered boxes (deduplicated by box ID).
            home_table: Table/collection name to store home device measurements in
        """
        self.api_client = api_client
        self.parser = parser
        self.database = database
        self.grouptags = grouptags if grouptags else ["atrai"]
        self.default_start_date = default_start_date if default_start_date else date(2024, 1, 1)
        self.home_grouptag = home_grouptag
        self.home_box_ids = home_box_ids if home_box_ids else []
        self.home_table = home_table
    
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

    def run_home_sync_job(self):
        """
        Execute a sync job for senseBox:home stations.

        Boxes come from two sources, merged and deduplicated by box ID:
        - self.home_grouptag: discovered dynamically, like run_sync_job() does for bikes
        - self.home_box_ids: specific boxes that aren't tagged with home_grouptag and so
          can't be discovered that way, fetched individually

        Data is stored in a separate table (self.home_table) so it never
        mixes with the grouptag-based bike sync's data.
        """
        if not self.home_grouptag and not self.home_box_ids:
            logger.info("No home devices configured, skipping home sync job")
            return

        boxes_by_id = {}

        if self.home_grouptag:
            logger.info(f"Fetching home devices with grouptag '{self.home_grouptag}'")
            for box in self.api_client.fetch_boxes(self.home_grouptag):
                boxes_by_id[box.id] = box
            logger.info(f"Found {len(boxes_by_id)} home device(s) for grouptag '{self.home_grouptag}'")

        for box_id in self.home_box_ids:
            if box_id in boxes_by_id:
                continue
            box = self.api_client.fetch_box_by_id(box_id)
            if box is None:
                logger.error(f"[home] Could not fetch box {box_id}")
                continue
            boxes_by_id[box.id] = box

        boxes = list(boxes_by_id.values())
        logger.info(f"Starting home-device sync job for {len(boxes)} box(es)")

        for i, box in enumerate(boxes, 1):
            try:
                logger.info(f"[home] [{i}/{len(boxes)}] Syncing box: {box.name} ({box.id})")
                self.sync_home_box(box)
                logger.info(f"[home] [{i}/{len(boxes)}] Successfully synced {box.name}")
            except Exception as e:
                logger.error(f"[home] [{i}/{len(boxes)}] Error syncing box {box.name} ({box.id}): {e}", exc_info=True)
                continue

        logger.info(f"Home-device sync job completed. Processed {len(boxes)} box(es)")

    def sync_box(self, box, start_date: Optional[date] = None, end_date: Optional[date] = None):
        """
        Sync data for a single (bike) box within date range.

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

        # No sync-state bookkeeping: the resume point is derived from the
        # latest stored measurement (see DatabaseManager.get_latest_sync_date).
        logger.info(f"Finished sync for {box.name} up to {end_date}")

    def process_day(self, box, target_date: date):
        """
        Process data for a single (bike) box and date.

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

    def sync_home_box(self, box, start_date: Optional[date] = None, end_date: Optional[date] = None):
        """
        Sync data for a single senseBox:home box within date range.

        Mirrors sync_box(), but resolves against self.home_table and delegates
        to process_home_day() instead — kept as a separate method (rather than
        a shared one with profile/table-name flags) since the bike and home
        device types have genuinely different data models.

        Args:
            box: Box object with id, name, sanitized_name, grouptags, and
                optionally a static longitude/latitude
            start_date: Optional start date for sync (inclusive). If None, determined from sync state.
            end_date: Optional end date for sync (inclusive). If None, defaults to today.
        """
        if end_date is None:
            end_date = date.today()

        if start_date is None:
            latest_sync_date = self.database.get_latest_sync_date(box.id, table_name=self.home_table)

            if latest_sync_date is None:
                start_date = self.default_start_date
                logger.info(f"No sync history for {box.name} ({box.id}), starting from {start_date}")
            else:
                start_date = latest_sync_date + timedelta(days=1)
                logger.info(f"Resuming sync for {box.name} ({box.id}) from {start_date}")

        current_date = start_date
        while current_date <= end_date:
            self.process_home_day(box, current_date)
            current_date += timedelta(days=1)

        logger.info(f"Finished sync for {box.name} up to {end_date}")

    def process_home_day(self, box, target_date: date):
        """
        Process data for a single senseBox:home box and date.

        Mirrors process_day(), but uses the home sensor-name mapping, builds
        HomeMeasurement objects, and writes to self.home_table via
        insert_home_measurements().

        Args:
            box: Box object with id, name, sanitized_name, grouptags, and
                optionally a static longitude/latitude
            target_date: Date to process
        """
        date_str = target_date.strftime('%Y-%m-%d')

        try:
            logger.info(f"Processing {box.name} ({box.id}) for date {date_str}")
            metadata = self.api_client.fetch_archive_metadata(
                box.id,
                box.sanitized_name,
                date_str
            )

            if metadata is None:
                logger.info(f"No archive data found for {box.name} on {date_str}")
                return

            try:
                box_metadata = self.parser.parse_metadata(json.dumps(metadata))
            except ValueError as e:
                logger.error(f"Failed to parse metadata for {box.name} on {date_str}: {e}")
                return

            measurements_by_timestamp = {}

            for sensor in box_metadata.sensors:
                sensor_id = sensor.get('_id')
                sensor_title = sensor.get('title', '')

                if not sensor_id:
                    continue

                column_name = self.parser.map_home_sensor_to_column(sensor_title)
                if column_name is None:
                    logger.debug(f"Skipping unmapped home sensor: {sensor_title}")
                    continue

                csv_content = self.api_client.fetch_archive_csv(
                    box.id,
                    box.sanitized_name,
                    date_str,
                    sensor_id
                )

                if csv_content is None:
                    logger.debug(f"No CSV data for sensor {sensor_title} ({sensor_id}) on {date_str}")
                    continue

                try:
                    parsed_data = self.parser.parse_csv(csv_content)
                except Exception as e:
                    logger.error(f"Failed to parse CSV for sensor {sensor_title}: {e}")
                    continue

                for data_point in parsed_data:
                    timestamp = data_point['timestamp']

                    # senseBox:home stations are stationary and have no
                    # per-measurement GPS sensor, so fall back to the box's
                    # static location (from OpenSenseMap's currentLocation).
                    if timestamp not in measurements_by_timestamp:
                        measurements_by_timestamp[timestamp] = {
                            'boxid': box.id,
                            'boxname': box.name,
                            'grouptags': json.dumps(box.grouptags),
                            'timestamp': timestamp,
                            'longitude': data_point.get('longitude') or getattr(box, 'longitude', None),
                            'latitude': data_point.get('latitude') or getattr(box, 'latitude', None),
                        }

                    if data_point.get('longitude') is not None:
                        measurements_by_timestamp[timestamp]['longitude'] = data_point['longitude']
                    if data_point.get('latitude') is not None:
                        measurements_by_timestamp[timestamp]['latitude'] = data_point['latitude']

                    measurements_by_timestamp[timestamp][column_name] = data_point['value']

            all_measurements = [
                HomeMeasurement(**measurement_data)
                for measurement_data in measurements_by_timestamp.values()
            ]

            if all_measurements:
                inserted_count = self.database.insert_home_measurements(all_measurements, table_name=self.home_table)
                logger.info(f"Processed {inserted_count} measurement records for {box.name} on {date_str}")
            else:
                logger.info(f"No measurements to insert for {box.name} on {date_str}")

        except Exception as e:
            logger.error(f"Error processing {box.name} on {date_str}: {e}")
