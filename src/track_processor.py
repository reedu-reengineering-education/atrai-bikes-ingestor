"""
Track Processing Module

Uses MovingPandas to:
1. Segment GPS points into individual tracks (stops detection)
2. Clean data (remove noise, stationary points)
3. Calculate track statistics (distance, duration, speed)
4. Store in tracks and track_points tables
"""

import logging
from typing import List, Optional, Tuple
from datetime import datetime, timedelta, date
from dataclasses import dataclass

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString
import movingpandas as mpd
import psycopg2
from psycopg2.extras import execute_batch

logger = logging.getLogger(__name__)


@dataclass
class TrackStats:
    """Statistics for a single track."""
    box_id: str
    box_name: str
    group_tags: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    distance_meters: float
    num_points: int
    avg_speed_ms: float
    max_speed_ms: float
    linestring: LineString
    start_point: Point
    end_point: Point
    avg_temperature: Optional[float]
    avg_humidity: Optional[float]
    avg_pm25: Optional[float]
    avg_pm10: Optional[float]
    avg_overtaking_distance: Optional[float]
    avg_distance_right: Optional[float]


class TrackProcessor:
    """Process raw GPS data into tracks using MovingPandas."""
    
    # Parameters for track segmentation
    STOP_RADIUS_METERS = 25  # Points within this radius are considered stopped
    STOP_DURATION_MINUTES = 1  # Minimum duration to be considered a stop (reduced from 2)
    MAX_SPEED_KMH = 50  # Max realistic bike speed (km/h); exceeding this indicates a jump/error
    MAX_DISTANCE_METERS = 500  # Max distance between consecutive points in one track
    MIN_TRACK_LENGTH_METERS = 50  # Minimum track length to store
    MIN_TRACK_POINTS = 3  # Minimum points to form a track
    
    def __init__(self, connection_string: str):
        """Initialize track processor with database connection."""
        self.connection_string = connection_string
    
    def fetch_unprocessed_data(self, conn) -> pd.DataFrame:
        """
        Fetch raw measurements that haven't been processed into tracks yet.

        For each box, only returns rows with createdAt strictly after the
        endTime of the latest existing track for that box.  This avoids
        re-processing already-segmented data on every sync run.
        """
        query = """
        SELECT
            o."boxId",
            o."boxName",
            o."groupTags",
            o."createdAt" as timestamp,
            o.longitude,
            o.latitude,
            o."Speed",
            o."Temperature",
            o."Rel. Humidity" as humidity,
            o."Finedust PM2.5" as pm25,
            o."Finedust PM10" as pm10,
            o."Overtaking Distance" as overtaking_distance,
            o."Distance Right" as distance_right
        FROM osem_bike_data o
        LEFT JOIN (
            SELECT "boxId", MAX("endTime") AS latest_end
            FROM tracks
            GROUP BY "boxId"
        ) t ON t."boxId" = o."boxId"
        WHERE o.longitude   IS NOT NULL
          AND o.latitude    IS NOT NULL
          AND o."createdAt" IS NOT NULL
          AND (t.latest_end IS NULL OR o."createdAt" > t.latest_end)
        ORDER BY o."boxId", o."createdAt"
        """
        return pd.read_sql(query, conn)
    
    def segment_into_tracks(self, data: pd.DataFrame) -> List[gpd.GeoDataFrame]:
        """
        Segment data into individual tracks per boxId based on time gaps, distance, and speed checks.
        
        Splits on:
        - Time gaps > STOP_DURATION_MINUTES
        - Distance jumps > MAX_DISTANCE_METERS
        - Implied speed > MAX_SPEED_KMH (unrealistic for bikes)
        """
        tracks = []
        
        for box_id, box_data in data.groupby("boxId"):
            if len(box_data) < self.MIN_TRACK_POINTS:
                logger.debug(f"Skipping {box_id}: too few points ({len(box_data)})")
                continue
            
            try:
                # Sort by timestamp
                box_data = box_data.sort_values("timestamp").reset_index(drop=True)
                box_data["timestamp"] = pd.to_datetime(box_data["timestamp"])
                
                # Calculate time gaps between consecutive points (in minutes)
                box_data["time_gap"] = box_data["timestamp"].diff().dt.total_seconds() / 60
                
                # Calculate distance between consecutive points using Haversine
                from math import radians, cos, sin, asin, sqrt
                
                def haversine_distance(lat1, lon1, lat2, lon2):
                    """Distance in meters between two lat/lon points."""
                    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
                    dlon = lon2 - lon1
                    dlat = lat2 - lat1
                    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                    c = 2 * asin(sqrt(a))
                    r = 6371000  # Radius of earth in meters
                    return c * r
                
                distances = []
                for i in range(len(box_data)):
                    if i == 0:
                        distances.append(0)
                    else:
                        dist = haversine_distance(
                            box_data["latitude"].iloc[i-1],
                            box_data["longitude"].iloc[i-1],
                            box_data["latitude"].iloc[i],
                            box_data["longitude"].iloc[i]
                        )
                        distances.append(dist)
                
                box_data["distance"] = distances
                
                # Calculate implied speed (m/s)
                box_data["implied_speed_ms"] = box_data["distance"] / (box_data["time_gap"] * 60)
                
                # Mark track boundaries
                # Split if: time gap too long, distance too large, or speed unrealistic
                box_data["new_track"] = (
                    (box_data["time_gap"] > self.STOP_DURATION_MINUTES) |  # Time gap
                    (box_data["distance"] > self.MAX_DISTANCE_METERS) |     # Distance jump
                    (box_data["implied_speed_ms"] > self.MAX_SPEED_KMH / 3.6)  # Speed (convert km/h to m/s)
                ).fillna(True)
                
                box_data["track_group"] = box_data["new_track"].cumsum()
                
                # Split into tracks
                for track_id, track_group in box_data.groupby("track_group"):
                    if len(track_group) < self.MIN_TRACK_POINTS:
                        continue
                    
                    # Create geometry
                    geometry = [
                        Point(xy) for xy in zip(track_group["longitude"], track_group["latitude"])
                    ]
                    track_gdf = gpd.GeoDataFrame(
                        track_group,
                        geometry=geometry,
                        crs="EPSG:4326"
                    )
                    
                    tracks.append(track_gdf)
                    
            except Exception as e:
                logger.error(f"Error processing trajectory for {box_id}: {e}", exc_info=True)
                continue
        
        logger.info(f"Segmented data into {len(tracks)} tracks")
        return tracks
    
    def calculate_track_stats(self, track_gdf: gpd.GeoDataFrame) -> Optional[TrackStats]:
        """
        Calculate statistics for a single track GeoDataFrame.
        
        Returns TrackStats with distance, duration, speed, aggregated sensor values.
        """
        if len(track_gdf) < self.MIN_TRACK_POINTS:
            return None
        
        try:
            track_gdf = track_gdf.sort_values("timestamp")
            
            box_id = str(track_gdf["boxId"].iloc[0])
            box_name = str(track_gdf["boxName"].iloc[0])
            group_tags = str(track_gdf["groupTags"].iloc[0]) if pd.notna(track_gdf["groupTags"].iloc[0]) else None
            
            start_time = pd.Timestamp(track_gdf["timestamp"].iloc[0]).to_pydatetime()
            end_time = pd.Timestamp(track_gdf["timestamp"].iloc[-1]).to_pydatetime()
            duration_seconds = float((end_time - start_time).total_seconds())
            
            # Calculate distance using PostGIS ST_Length
            coords = list(zip(track_gdf["longitude"], track_gdf["latitude"]))
            if len(coords) < 2:
                return None
            
            linestring = LineString(coords)
            # Distance in meters (convert from degrees using rough approximation)
            distance_meters = float(linestring.length * 111320)  # 1 degree ≈ 111.32 km
            
            # Speed statistics
            speeds = pd.to_numeric(track_gdf["Speed"], errors="coerce").dropna()
            avg_speed_ms = float(speeds.mean()) if len(speeds) > 0 else None
            max_speed_ms = float(speeds.max()) if len(speeds) > 0 else None
            
            # Start and end points
            start_point = Point(float(track_gdf["longitude"].iloc[0]), float(track_gdf["latitude"].iloc[0]))
            end_point = Point(float(track_gdf["longitude"].iloc[-1]), float(track_gdf["latitude"].iloc[-1]))
            
            # Aggregated sensor values - convert to Python float
            avg_temperature = pd.to_numeric(track_gdf["Temperature"], errors="coerce").mean()
            avg_temperature = float(avg_temperature) if pd.notna(avg_temperature) else None
            
            avg_humidity = pd.to_numeric(track_gdf["humidity"], errors="coerce").mean()
            avg_humidity = float(avg_humidity) if pd.notna(avg_humidity) else None
            
            avg_pm25 = pd.to_numeric(track_gdf["pm25"], errors="coerce").mean()
            avg_pm25 = float(avg_pm25) if pd.notna(avg_pm25) else None
            
            avg_pm10 = pd.to_numeric(track_gdf["pm10"], errors="coerce").mean()
            avg_pm10 = float(avg_pm10) if pd.notna(avg_pm10) else None
            
            avg_overtaking_distance = pd.to_numeric(track_gdf["overtaking_distance"], errors="coerce").mean()
            avg_overtaking_distance = float(avg_overtaking_distance) if pd.notna(avg_overtaking_distance) else None
            
            avg_distance_right = pd.to_numeric(track_gdf["distance_right"], errors="coerce").mean()
            avg_distance_right = float(avg_distance_right) if pd.notna(avg_distance_right) else None
            
            return TrackStats(
                box_id=box_id,
                box_name=box_name,
                group_tags=group_tags,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                distance_meters=distance_meters,
                num_points=len(track_gdf),
                avg_speed_ms=avg_speed_ms,
                max_speed_ms=max_speed_ms,
                linestring=linestring,
                start_point=start_point,
                end_point=end_point,
                avg_temperature=avg_temperature,
                avg_humidity=avg_humidity,
                avg_pm25=avg_pm25,
                avg_pm10=avg_pm10,
                avg_overtaking_distance=avg_overtaking_distance,
                avg_distance_right=avg_distance_right,
            )
        except Exception as e:
            logger.error(f"Error calculating track stats: {e}", exc_info=True)
            return None
    
    def store_tracks(self, tracks: List[gpd.GeoDataFrame], conn) -> int:
        """
        Store tracks in database.
        
        For each track:
        1. Calculate statistics
        2. Insert into tracks table
        3. Insert points into track_points table
        
        Returns number of tracks stored.
        """
        stored_count = 0
        
        with conn.cursor() as cursor:
            for track_gdf in tracks:
                # Calculate stats
                stats = self.calculate_track_stats(track_gdf)
                if not stats or stats.distance_meters < self.MIN_TRACK_LENGTH_METERS:
                    continue
                
                try:
                    # Insert track record — ON CONFLICT DO NOTHING makes this idempotent
                    cursor.execute("""
                        INSERT INTO tracks (
                            "boxId", "boxName", "groupTags",
                            "startTime", "endTime", "duration_seconds",
                            "distance_meters", "num_points",
                            "avg_speed_ms", "max_speed_ms",
                            "linestring_geometry", "start_geometry", "end_geometry",
                            "avg_temperature", "avg_humidity", "avg_pm25", "avg_pm10",
                            "avg_overtaking_distance", "avg_distance_right",
                            "processed_at"
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                  ST_GeomFromText(%s, 4326), ST_GeomFromText(%s, 4326),
                                  ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT ("boxId", "startTime", "endTime") DO NOTHING
                        RETURNING id
                    """, (
                        stats.box_id, stats.box_name, stats.group_tags,
                        stats.start_time, stats.end_time, stats.duration_seconds,
                        stats.distance_meters, stats.num_points,
                        stats.avg_speed_ms, stats.max_speed_ms,
                        f"SRID=4326;{stats.linestring.wkt}",
                        f"SRID=4326;{stats.start_point.wkt}",
                        f"SRID=4326;{stats.end_point.wkt}",
                        stats.avg_temperature, stats.avg_humidity, stats.avg_pm25, stats.avg_pm10,
                        stats.avg_overtaking_distance, stats.avg_distance_right,
                        datetime.now()
                    ))
                    
                    row = cursor.fetchone()
                    if row is None:
                        # Conflict: track already exists, skip
                        continue
                    track_id = row[0]
                    
                    # Insert track points
                    track_gdf = track_gdf.sort_values("timestamp")
                    for seq, (_, row) in enumerate(track_gdf.iterrows()):
                        cursor.execute("""
                            INSERT INTO track_points (
                                track_id, "boxId", "timestamp", "sequence",
                                longitude, latitude, geometry,
                                "speed_ms", "temperature", "humidity", "pm25", "pm10",
                                "overtaking_distance", "distance_right"
                            ) VALUES (%s, %s, %s, %s, %s, %s, 
                                      ST_GeomFromText(%s, 4326), %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            track_id, row["boxId"], row["timestamp"], seq,
                            row["longitude"], row["latitude"],
                            f"SRID=4326;POINT({row['longitude']} {row['latitude']})",
                            row.get("Speed"), row.get("Temperature"),
                            row.get("humidity"), row.get("pm25"), row.get("pm10"),
                            row.get("overtaking_distance"), row.get("distance_right")
                        ))
                    
                    conn.commit()
                    stored_count += 1
                    logger.info(f"Stored track for {stats.box_id}: {stats.distance_meters:.0f}m, {stats.duration_seconds:.0f}s")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Error storing track: {e}", exc_info=True)
                    continue
        
        logger.info(f"Stored {stored_count} tracks to database")
        return stored_count
    
    def process(self) -> int:
        """
        Main entry point: fetch data, segment, calculate stats, store.
        
        Returns number of tracks stored.
        """
        try:
            conn = psycopg2.connect(self.connection_string)
            
            logger.info("Fetching unprocessed GPS data...")
            data = self.fetch_unprocessed_data(conn)
            
            if data.empty:
                logger.info("No new data to process")
                return 0
            
            logger.info(f"Processing {len(data)} measurements into tracks...")
            tracks = self.segment_into_tracks(data)
            
            if not tracks:
                logger.info("No valid tracks found")
                return 0
            
            logger.info(f"Storing {len(tracks)} tracks to database...")
            count = self.store_tracks(tracks, conn)
            
            conn.close()
            return count
            
        except Exception as e:
            logger.error(f"Track processing failed: {e}", exc_info=True)
            return 0
