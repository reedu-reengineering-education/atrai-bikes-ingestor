from .process_base import BaseProcessor, ProcessorExecuteError
from .atrai_processor import AtraiProcessor
from datetime import timedelta
import logging
import json
import pandas as pd
from config.db_config import DatabaseConfig 
from .stop_detection import load_bike_data_from_db, analyze_trajectories

LOGGER = logging.getLogger(__name__)

METADATA = {
    "version": "1.0.0",
    "id": "traffic-stops-detector",
    "title": {
        "en": "Traffic Stop Detection",
    },
    "description": {"en": "Identifies stationary periods, i.e. stops, for a specified boxId or campaign within a given time range "},
    "jobControlOptions": ["sync-execute", "async-execute"],
    "keywords": ["movingpandas", "trajectory","stop detection"],
    "links": [
        {
            "type": "text/html",
            "rel": "about",
            "title": "information",
            "href": "https://example.org/process",
            "hreflang": "en-US",
        }
    ],
    "inputs": {
        "boxId": {
            "title": "boxId",
            "description": "boxId to get the data from",
            "schema": {"type": "string"},
        },
        "startDate": {
            "title": "Start date (optional)",
            "description": "Start datetime for the stop detection analysis (YYYY-MM-DDTHH:MM:SSZ)", #sample createdAt from db 2024-10-30 17:58:11.026
            "schema": {"type": "string", "format": "date-time"},
            "minOccurs": 0, 
            "maxOccurs": 1, 
        },
        "endDate": {
            "title": "End date (optional)",
            "description": "End datetime for the stop detection analysis (YYYY-MM-DDTHH:MM:SSZ)", #sample createdAt from db 2024-10-30 17:58:11.026
            "schema": {"type": "string", "format": "date-time"},
            "minOccurs": 1, 
            "maxOccurs": 1, 
        },
        "maxDiameter": {
            "title": "Max Diameter (m)",
            "description": "Define the max diameter in meters for the stop cluster", 
            "schema": {"type": "number", "default": 50.0},
            "minOccurs": 1, 
            "maxOccurs": 1, 
        },
        "minDuration": {
            "title": "Min Duration (min)",
            "description": "Minimum time in minutes for a cluster to be considered a stop.",
            "schema": {"type": "number", "default": 2.0},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
        "token": {
            "title": "secret token",
            "description": "identify yourself",
            "schema": {"type": "string"},
        },
    },
    "outputs": {
        "stop_points": {
            "title": "Detected Stop Points",
            "description": "GeoJSON feature collections of calculated stopping points",
            "schema": {"type": "string"},
        },
    },
    "example": {
        "inputs": {
            "boxId": "ABCDEF123456", 
            "startDate": "2024-01-01 00:00:00", 
            "endDate": "2024-01-02 23:59:59", 
            "maxDiameter": 50.0, 
            "minDuration": 2.0,
            "token": "ABC123XYZ",
        },
    },
}

class TrafficStops(AtraiProcessor):
    """Traffic Stop Detection Processor"""

    def __init__(self, processor_def):
        """Initialize TrafficStops Processor."""
        super().__init__(processor_def, METADATA) 
        self.output_mimetype = 'application/geo+json'

    def execute(self, data):
        """
        Executes the Traffic Stop Detection process, with priority for campaign 
        filtering if provided, otherwise using explicit boxId list
        """

        campaign_input = data.get('campaign')
    
        if campaign_input:
            # Resolve box IDs for the campaign/grouptag via the OpenSenseMap API
            matched_ids = self._get_box_ids_for_grouptag(campaign_input)
            if matched_ids:
                data['boxId'] = matched_ids
                data['campaign'] = None
                LOGGER.info(f"Found {len(matched_ids)} boxes for campaign '{campaign_input}'")
        
        self.check_request_params(data)

        # Parse and validate inputs
        max_diameter = data.get('maxDiameter', 50.0)
        min_duration_min = data.get('minDuration', 2.0)        
        min_duration = timedelta(minutes=min_duration_min) # Convert minutes to timedelta

        if self.campaign or self.boxId: 
            box_id_list = self.boxId
            if not box_id_list: 
                raise ProcessorExecuteError(f"No box IDs found for campaign '{self.campaign}'")

            # Data Loading from PostgreSQL
            try:
                # Use the helper function from stop_detection.py and pass the engine provided by the base processor
                gdf = load_bike_data_from_db(
                    box_id=box_id_list,
                    start_date=self.t_start,
                    end_date=self.t_end,
                    db_engine=self.db_engine 
                )
            except Exception as e:
                LOGGER.error(f"Error loading data from DB: {e}")
                raise 
        else: 
            raise ProcessorExecuteError("Must provide 'campaign' or 'boxId' for filtering")

        if gdf.empty:
            outputs = {
                "id": "stop_points",
                "message": f"No data found for filter set (Campaign: {self.campaign}, BoxIDs: {self.boxId}) in the specified range."
            }
            return self.output_mimetype, outputs
        
        # Trajectory Analysis and Stop Detection
        try:
            stops_gdf = analyze_trajectories(
                gdf=gdf,
                id_col='boxId',
                max_diam=max_diameter,
                min_dur=min_duration
            )
        except Exception as e:
            LOGGER.error(f"MovingPandas analysis failed: {e}")
            raise ProcessorExecuteError(f"Analysis error: {e}")
        
        # Save results to postgres
        
        RESULTS_TABLE_NAME = "detected_traffic_stops"
        LOGGER.info(f"Saving {len(stops_gdf)} detected stops to PostGIS table: {RESULTS_TABLE_NAME}")

        if not stops_gdf.empty:
            try:
                LOGGER.info(f"Attempting to write {len(stops_gdf)} rows to {RESULTS_TABLE_NAME}")
                with self.db_engine.begin() as connection: 
                    # Use to_postgis to write the gdf back to postgres
                    stops_gdf.to_postgis(
                        RESULTS_TABLE_NAME,
                        # self.db_engine,
                        connection,
                        if_exists="append", 
                        index=True,
                        schema='public' 
                    )
                    LOGGER.info(f"Successfully committed {RESULTS_TABLE_NAME} to PostGIS")
            except Exception as e:
                LOGGER.error(f"Failed to write results to PostGIS: {e}")
                # Log the failure but still continue to return the geojson result
        
        # Remove the internal mpd ID column to clean up the output
        if 'MP_ID' in stops_gdf.columns:
            stops_gdf = stops_gdf.drop(columns=['MP_ID'])

        if stops_gdf.empty:
            feature_collection = {"type": "FeatureCollection", "features": []}
            message = f"No stops detected for boxId with criteria: {max_diameter}m / {min_duration_min}min."
        else:
            # Convert timestamps to strings for JSON compatibility before converting the gdf to json
            for col in stops_gdf.columns:
                if pd.api.types.is_datetime64_any_dtype(stops_gdf[col]):
                    stops_gdf[col] = stops_gdf[col].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            # Convert the gdf to a geojson feature collections dictionary
            feature_collection = json.loads(stops_gdf.to_json())
            message = f"Successfully detected {len(stops_gdf)} stops."

        outputs = {
            "id": "stop_points",
            "message": message,
            "stop_points": feature_collection
        }

        # Return results to pygeoapi
        return self.output_mimetype, outputs

    def __repr__(self):
        return f"<TrafficStops> {self.name}"