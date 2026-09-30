"""
Data Parser for OpenSenseMap Archive Files

This module provides functionality to parse CSV sensor data and JSON metadata
from OpenSenseMap archive files.
"""

import csv
import json
import logging
from typing import List, Optional, Dict
from dataclasses import dataclass
from datetime import datetime
from io import StringIO

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class Measurement:
    """Represents a single senseBox:bike sensor measurement."""
    boxid: str
    boxname: str
    grouptags: str  # JSON array as string
    timestamp: datetime
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pm1: Optional[float] = None
    pm2_5: Optional[float] = None
    pm4: Optional[float] = None
    pm10: Optional[float] = None
    overtaking_distance: Optional[float] = None
    overtaking_maneuvre: Optional[int] = None
    standing: Optional[int] = None
    asphalt: Optional[int] = None
    compacted: Optional[int] = None
    paving: Optional[int] = None
    sett: Optional[int] = None
    speed: Optional[float] = None
    distance_right: Optional[float] = None


@dataclass
class HomeMeasurement:
    """Represents a single senseBox:home / weather-station sensor measurement.

    Separate from Measurement (senseBox:bike) because the two device types
    report genuinely different phenomena — no overtaking/surface/speed here,
    and no pressure/wind/rain/UV on the bikes.
    """
    boxid: str
    boxname: str
    grouptags: str  # JSON array as string
    timestamp: datetime
    longitude: Optional[float] = None
    latitude: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    illuminance: Optional[float] = None
    uv: Optional[float] = None
    uv_index: Optional[float] = None
    pm1: Optional[float] = None
    pm2_5: Optional[float] = None
    pm4: Optional[float] = None
    pm10: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_gust: Optional[float] = None
    wind_direction: Optional[float] = None
    rain_rate: Optional[float] = None
    dewpoint: Optional[float] = None
    solar_radiation: Optional[float] = None
    cloud_base: Optional[float] = None


@dataclass
class BoxMetadata:
    """Represents box metadata from JSON files."""
    box_id: str
    box_name: str
    grouptags: List[str]
    sensors: List[Dict]


class DataParser:
    """Parser for OpenSenseMap CSV and JSON data."""
    
    # Sensor name to database column mapping (case-insensitive)
    SENSOR_COLUMN_MAP = {
        'temperature': 'temperature',
        'humidity': 'humidity',
        'rel. humidity': 'humidity',
        'pm1': 'pm1',
        'finedust pm1': 'pm1',
        'pm2.5': 'pm2_5',
        'finedust pm2.5': 'pm2_5',
        'pm4': 'pm4',
        'finedust pm4': 'pm4',
        'pm10': 'pm10',
        'finedust pm10': 'pm10',
        'overtaking_distance': 'overtaking_distance',
        'overtaking distance': 'overtaking_distance',
        'distance left': 'overtaking_distance',
        'distance_left': 'overtaking_distance',
        'distance right': 'distance_right',
        'distance_right': 'distance_right',
        'overtaking_maneuvre': 'overtaking_maneuvre',
        'overtaking_manoeuvre': 'overtaking_maneuvre',
        'overtaking manoeuvre': 'overtaking_maneuvre',
        'standing': 'standing',
        'asphalt': 'asphalt',
        'surface asphalt': 'asphalt',
        'compacted': 'compacted',
        'surface compacted': 'compacted',
        'paving': 'paving',
        'surface paving': 'paving',
        'sett': 'sett',
        'surface sett': 'sett',
        'speed': 'speed',
    }

    # Sensor name to database column mapping for senseBox:home / weather-station
    # devices (case-insensitive). These boxes use German titles and a different
    # phenomenon set than the bike sensors above (see SENSOR_COLUMN_MAP), so
    # they get their own map rather than polluting the bike one.
    HOME_SENSOR_COLUMN_MAP = {
        'temperatur': 'temperature',
        'temperature': 'temperature',
        'rel. luftfeuchte': 'humidity',
        'relative luftfeuchte': 'humidity',
        'luftfeuchte': 'humidity',
        'humid': 'humidity',
        'humidity': 'humidity',
        'rel. humidity': 'humidity',
        'luftdruck': 'pressure',
        'luftdruck (nn)': 'pressure',
        'pressure': 'pressure',
        'beleuchtungsstärke': 'illuminance',
        'ambient light': 'illuminance',
        'illuminance': 'illuminance',
        'uv-intensität': 'uv',
        'uv intensity': 'uv',
        'uv-index': 'uv_index',
        'uv index': 'uv_index',
        'pm1': 'pm1',
        'pm25': 'pm2_5',
        'pm2.5': 'pm2_5',
        'pm4': 'pm4',
        'pm10': 'pm10',
        'windgeschwindigkeit': 'wind_speed',
        'windspeed': 'wind_speed',
        'wind speed': 'wind_speed',
        'windgust': 'wind_gust',
        'wind gust': 'wind_gust',
        'windrichtung': 'wind_direction',
        'wind direction': 'wind_direction',
        'rain rate': 'rain_rate',
        'regenrate': 'rain_rate',
        'dewpoint': 'dewpoint',
        'taupunkt': 'dewpoint',
        'solar radiation': 'solar_radiation',
        'globalstrahlung': 'solar_radiation',
        'wolkenbasis': 'cloud_base',
        'cloud base': 'cloud_base',
    }

    def parse_csv(self, csv_content: str) -> List[Measurement]:
        """
        Parse CSV sensor data into measurement objects.
        
        Args:
            csv_content: The CSV content as a string
            
        Returns:
            List of Measurement objects (as dictionaries with timestamp, value, longitude, latitude)
        """
        measurements = []
        
        try:
            # Use StringIO to treat string as file-like object
            csv_file = StringIO(csv_content)
            reader = csv.DictReader(csv_file)
            
            for row in reader:
                try:
                    # Extract timestamp and value from CSV row
                    # Expected format: createdAt, value, longitude, latitude
                    timestamp_str = row.get('createdAt', '').strip()
                    value_str = row.get('value', '').strip()
                    longitude_str = row.get('longitude', '').strip()
                    latitude_str = row.get('latitude', '').strip()
                    
                    if not timestamp_str or not value_str:
                        continue
                    
                    # Parse timestamp - handle ISO 8601 format
                    # Example: 2024-01-01T12:00:00.000Z
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    
                    # Parse value - could be float or int
                    try:
                        value = float(value_str)
                    except ValueError:
                        logger.warning(f"Invalid value in CSV: {value_str}")
                        continue
                    
                    # Parse GPS coordinates if available
                    longitude = None
                    latitude = None
                    
                    if longitude_str:
                        try:
                            longitude = float(longitude_str)
                        except ValueError:
                            logger.debug(f"Invalid longitude in CSV: {longitude_str}")
                    
                    if latitude_str:
                        try:
                            latitude = float(latitude_str)
                        except ValueError:
                            logger.debug(f"Invalid latitude in CSV: {latitude_str}")
                    
                    # Create a basic measurement object
                    # Note: boxid, boxname, grouptags, and sensor type will be set by caller
                    measurement = {
                        'timestamp': timestamp,
                        'value': value,
                        'longitude': longitude,
                        'latitude': latitude
                    }
                    measurements.append(measurement)
                    
                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing CSV row: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing CSV content: {e}")
        
        return measurements
    
    def parse_metadata(self, json_content: str) -> BoxMetadata:
        """
        Parse JSON metadata into structured format.
        
        Args:
            json_content: The JSON content as a string
            
        Returns:
            BoxMetadata object
            
        Raises:
            ValueError: If JSON is malformed or missing required fields
        """
        try:
            data = json.loads(json_content)
            
            # Extract required fields
            box_id = data.get('id', '')
            box_name = data.get('name', '')
            grouptags = data.get('grouptag', [])
            sensors = data.get('sensors', [])
            
            if not box_id or not box_name:
                raise ValueError("Missing required fields: _id or name")
            
            # Ensure grouptags is a list
            if not isinstance(grouptags, list):
                grouptags = []
            
            # Ensure sensors is a list
            if not isinstance(sensors, list):
                sensors = []
            
            return BoxMetadata(
                box_id=box_id,
                box_name=box_name,
                grouptags=grouptags,
                sensors=sensors
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
            raise ValueError(f"Malformed JSON: {e}")
        except Exception as e:
            logger.error(f"Error parsing metadata: {e}")
            raise ValueError(f"Error parsing metadata: {e}")
    
    def map_sensor_to_column(self, sensor_name: str) -> Optional[str]:
        """
        Map sensor names to database column names.
        
        Args:
            sensor_name: The sensor name from the archive
            
        Returns:
            Database column name, or None if not mapped
        """
        if not sensor_name:
            return None
        
        # Convert to lowercase for case-insensitive matching
        sensor_name_lower = sensor_name.lower().strip()
        
        # Look up in the mapping
        return self.SENSOR_COLUMN_MAP.get(sensor_name_lower)

    def map_home_sensor_to_column(self, sensor_name: str) -> Optional[str]:
        """
        Map senseBox:home sensor names to database column names.

        Args:
            sensor_name: The sensor name from the archive

        Returns:
            Database column name, or None if not mapped
        """
        if not sensor_name:
            return None

        return self.HOME_SENSOR_COLUMN_MAP.get(sensor_name.lower().strip())
