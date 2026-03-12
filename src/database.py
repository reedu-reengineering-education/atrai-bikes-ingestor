"""
Database Manager for PostGIS

This module provides functionality to manage database connections and operations
for storing sensor measurements in a PostGIS database.
"""

from typing import List, Optional
from datetime import date
import psycopg2
from psycopg2.extras import execute_batch
from psycopg2.pool import SimpleConnectionPool


class DatabaseManager:
    """Manager for database connections and operations."""
    
    def __init__(self, connection_string: str, min_connections: int = 1, max_connections: int = 10):
        """
        Initialize database connection.
        
        Args:
            connection_string: PostgreSQL connection string
            min_connections: Minimum number of connections in the pool
            max_connections: Maximum number of connections in the pool
        """
        self.connection_string = connection_string
        self.pool = SimpleConnectionPool(min_connections, max_connections, connection_string)
    
    def create_schema(self):
        """
        Create database tables and indexes if they don't exist.
        
        Creates:
            - osem_bike_data table with all sensor columns
            - sync_state table for tracking synchronization
            - indexes on boxid and timestamp columns
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Create osem_bike_data table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS osem_bike_data (
                        id SERIAL PRIMARY KEY,
                        boxid VARCHAR(255) NOT NULL,
                        boxname VARCHAR(255) NOT NULL,
                        grouptags TEXT,
                        timestamp TIMESTAMP NOT NULL,
                        longitude DOUBLE PRECISION,
                        latitude DOUBLE PRECISION,
                        temperature DOUBLE PRECISION,
                        humidity DOUBLE PRECISION,
                        pm1 DOUBLE PRECISION,
                        pm2_5 DOUBLE PRECISION,
                        pm4 DOUBLE PRECISION,
                        pm10 DOUBLE PRECISION,
                        overtaking_distance DOUBLE PRECISION,
                        overtaking_maneuvre INTEGER,
                        standing INTEGER,
                        asphalt INTEGER,
                        compacted INTEGER,
                        paving INTEGER,
                        sett INTEGER,
                        speed DOUBLE PRECISION,
                        distance_right DOUBLE PRECISION,
                        geom geometry(Point, 4326),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(boxid, timestamp)
                    );
                """)
                
                # Create indexes on osem_bike_data table
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid 
                    ON osem_bike_data(boxid);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_timestamp 
                    ON osem_bike_data(timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid_timestamp 
                    ON osem_bike_data(boxid, timestamp);
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_geom 
                    ON osem_bike_data USING GIST (geom);
                """)
                
                # Create sync_state table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_state (
                        boxid VARCHAR(255) PRIMARY KEY,
                        latest_sync_date DATE NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                conn.commit()
        finally:
            self.pool.putconn(conn)
    
    def insert_measurements(self, measurements: List) -> int:
        """
        Insert or update measurements into the database.
        
        Uses ON CONFLICT DO UPDATE to merge multiple phenomena into the same row.
        This allows multiple sensor readings (temperature, humidity, etc.) to be
        combined into a single measurement record per (boxid, timestamp).
        
        Args:
            measurements: List of Measurement objects
            
        Returns:
            Number of rows inserted or updated
        """
        if not measurements:
            return 0
        
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Prepare the INSERT statement with ON CONFLICT DO UPDATE
                # This will merge multiple phenomena into the same row
                insert_query = """
                    INSERT INTO osem_bike_data (
                        boxid, boxname, grouptags, timestamp, longitude, latitude,
                        temperature, humidity, pm1, pm2_5, pm4, pm10,
                        overtaking_distance, overtaking_maneuvre, standing,
                        asphalt, compacted, paving, sett, speed, distance_right, geom
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL 
                             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) 
                             ELSE NULL END
                    )
                    ON CONFLICT (boxid, timestamp) DO UPDATE SET
                        boxname = COALESCE(EXCLUDED.boxname, osem_bike_data.boxname),
                        grouptags = COALESCE(EXCLUDED.grouptags, osem_bike_data.grouptags),
                        longitude = COALESCE(EXCLUDED.longitude, osem_bike_data.longitude),
                        latitude = COALESCE(EXCLUDED.latitude, osem_bike_data.latitude),
                        temperature = COALESCE(EXCLUDED.temperature, osem_bike_data.temperature),
                        humidity = COALESCE(EXCLUDED.humidity, osem_bike_data.humidity),
                        pm1 = COALESCE(EXCLUDED.pm1, osem_bike_data.pm1),
                        pm2_5 = COALESCE(EXCLUDED.pm2_5, osem_bike_data.pm2_5),
                        pm4 = COALESCE(EXCLUDED.pm4, osem_bike_data.pm4),
                        pm10 = COALESCE(EXCLUDED.pm10, osem_bike_data.pm10),
                        overtaking_distance = COALESCE(EXCLUDED.overtaking_distance, osem_bike_data.overtaking_distance),
                        overtaking_maneuvre = COALESCE(EXCLUDED.overtaking_maneuvre, osem_bike_data.overtaking_maneuvre),
                        standing = COALESCE(EXCLUDED.standing, osem_bike_data.standing),
                        asphalt = COALESCE(EXCLUDED.asphalt, osem_bike_data.asphalt),
                        compacted = COALESCE(EXCLUDED.compacted, osem_bike_data.compacted),
                        paving = COALESCE(EXCLUDED.paving, osem_bike_data.paving),
                        sett = COALESCE(EXCLUDED.sett, osem_bike_data.sett),
                        speed = COALESCE(EXCLUDED.speed, osem_bike_data.speed),
                        distance_right = COALESCE(EXCLUDED.distance_right, osem_bike_data.distance_right),
                        geom = COALESCE(EXCLUDED.geom, osem_bike_data.geom);
                """
                
                # Prepare data tuples (longitude/latitude repeated for geom construction)
                data = [
                    (
                        m.boxid, m.boxname, m.grouptags, m.timestamp, m.longitude, m.latitude,
                        m.temperature, m.humidity, m.pm1, m.pm2_5, m.pm4, m.pm10,
                        m.overtaking_distance, m.overtaking_maneuvre, m.standing,
                        m.asphalt, m.compacted, m.paving, m.sett, m.speed, m.distance_right,
                        m.longitude, m.latitude, m.longitude, m.latitude  # for geom CASE WHEN and ST_MakePoint
                    )
                    for m in measurements
                ]
                
                # Execute batch upsert
                execute_batch(cursor, insert_query, data)
                
                # Get number of affected rows
                rows_affected = cursor.rowcount
                
                conn.commit()
                
                return rows_affected
        except Exception as e:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def get_latest_sync_date(self, box_id: str) -> Optional[date]:
        """
        Get the latest sync date for a box.
        
        Args:
            box_id: The box ID
            
        Returns:
            Latest sync date, or None if no sync history exists
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT latest_sync_date FROM sync_state WHERE boxid = %s;",
                    (box_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        finally:
            self.pool.putconn(conn)
    
    def update_sync_state(self, box_id: str, sync_date: date):
        """
        Update the sync state for a box.
        
        Args:
            box_id: The box ID
            sync_date: The date to record as the latest sync date
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Use INSERT ... ON CONFLICT UPDATE to handle both insert and update
                cursor.execute("""
                    INSERT INTO sync_state (boxid, latest_sync_date, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (boxid) 
                    DO UPDATE SET 
                        latest_sync_date = EXCLUDED.latest_sync_date,
                        updated_at = CURRENT_TIMESTAMP;
                """, (box_id, sync_date))
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)
    
    def close(self):
        """Close all database connections in the pool."""
        if self.pool:
            self.pool.closeall()
