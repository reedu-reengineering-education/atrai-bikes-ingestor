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
            - indexes on boxId and createdAt columns
            
        NOTE: Column names match OpenSenseMapToolbox output format for 
        compatibility with existing pygeoapi processes.
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Create osem_bike_data table with OpenSenseMapToolbox-compatible column names
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS osem_bike_data (
                        index SERIAL PRIMARY KEY,
                        "boxId" VARCHAR(255) NOT NULL,
                        "boxName" VARCHAR(255) NOT NULL,
                        "groupTags" TEXT,
                        "createdAt" TIMESTAMP NOT NULL,
                        longitude DOUBLE PRECISION,
                        latitude DOUBLE PRECISION,
                        "Temperature" DOUBLE PRECISION,
                        "Rel. Humidity" DOUBLE PRECISION,
                        "Finedust PM1" DOUBLE PRECISION,
                        "Finedust PM2.5" DOUBLE PRECISION,
                        "Finedust PM4" DOUBLE PRECISION,
                        "Finedust PM10" DOUBLE PRECISION,
                        "Overtaking Distance" DOUBLE PRECISION,
                        "Overtaking Manoeuvre" INTEGER,
                        "Standing" INTEGER,
                        "Surface Asphalt" INTEGER,
                        "Surface Compacted" INTEGER,
                        "Surface Paving" INTEGER,
                        "Surface Sett" INTEGER,
                        "Speed" DOUBLE PRECISION,
                        "Distance Right" DOUBLE PRECISION,
                        geometry geometry(Point, 4326),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE("boxId", "createdAt")
                    );
                """)
                
                # Create indexes on osem_bike_data table
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid 
                    ON osem_bike_data("boxId");
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_timestamp 
                    ON osem_bike_data("createdAt");
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid_timestamp 
                    ON osem_bike_data("boxId", "createdAt");
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_osem_bike_data_geom 
                    ON osem_bike_data USING GIST (geometry);
                """)
                
                # Create sync_state table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sync_state (
                        "boxId" VARCHAR(255) PRIMARY KEY,
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
        combined into a single measurement record per (boxId, createdAt).
        
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
                # Column names match OpenSenseMapToolbox output format
                insert_query = """
                    INSERT INTO osem_bike_data (
                        "boxId", "boxName", "groupTags", "createdAt", longitude, latitude,
                        "Temperature", "Rel. Humidity", "Finedust PM1", "Finedust PM2.5", "Finedust PM4", "Finedust PM10",
                        "Overtaking Distance", "Overtaking Manoeuvre", "Standing",
                        "Surface Asphalt", "Surface Compacted", "Surface Paving", "Surface Sett", "Speed", "Distance Right", geometry
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL 
                             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326) 
                             ELSE NULL END
                    )
                    ON CONFLICT ("boxId", "createdAt") DO UPDATE SET
                        "boxName" = COALESCE(EXCLUDED."boxName", osem_bike_data."boxName"),
                        "groupTags" = COALESCE(EXCLUDED."groupTags", osem_bike_data."groupTags"),
                        longitude = COALESCE(EXCLUDED.longitude, osem_bike_data.longitude),
                        latitude = COALESCE(EXCLUDED.latitude, osem_bike_data.latitude),
                        "Temperature" = COALESCE(EXCLUDED."Temperature", osem_bike_data."Temperature"),
                        "Rel. Humidity" = COALESCE(EXCLUDED."Rel. Humidity", osem_bike_data."Rel. Humidity"),
                        "Finedust PM1" = COALESCE(EXCLUDED."Finedust PM1", osem_bike_data."Finedust PM1"),
                        "Finedust PM2.5" = COALESCE(EXCLUDED."Finedust PM2.5", osem_bike_data."Finedust PM2.5"),
                        "Finedust PM4" = COALESCE(EXCLUDED."Finedust PM4", osem_bike_data."Finedust PM4"),
                        "Finedust PM10" = COALESCE(EXCLUDED."Finedust PM10", osem_bike_data."Finedust PM10"),
                        "Overtaking Distance" = COALESCE(EXCLUDED."Overtaking Distance", osem_bike_data."Overtaking Distance"),
                        "Overtaking Manoeuvre" = COALESCE(EXCLUDED."Overtaking Manoeuvre", osem_bike_data."Overtaking Manoeuvre"),
                        "Standing" = COALESCE(EXCLUDED."Standing", osem_bike_data."Standing"),
                        "Surface Asphalt" = COALESCE(EXCLUDED."Surface Asphalt", osem_bike_data."Surface Asphalt"),
                        "Surface Compacted" = COALESCE(EXCLUDED."Surface Compacted", osem_bike_data."Surface Compacted"),
                        "Surface Paving" = COALESCE(EXCLUDED."Surface Paving", osem_bike_data."Surface Paving"),
                        "Surface Sett" = COALESCE(EXCLUDED."Surface Sett", osem_bike_data."Surface Sett"),
                        "Speed" = COALESCE(EXCLUDED."Speed", osem_bike_data."Speed"),
                        "Distance Right" = COALESCE(EXCLUDED."Distance Right", osem_bike_data."Distance Right"),
                        geometry = COALESCE(EXCLUDED.geometry, osem_bike_data.geometry);
                """
                
                # Prepare data tuples (longitude/latitude repeated for geom construction)
                data = [
                    (
                        m.boxid, m.boxname, m.grouptags, m.timestamp, m.longitude, m.latitude,
                        m.temperature, m.humidity, m.pm1, m.pm2_5, m.pm4, m.pm10,
                        m.overtaking_distance, m.overtaking_maneuvre, m.standing,
                        m.asphalt, m.compacted, m.paving, m.sett, m.speed, m.distance_right,
                        m.longitude, m.latitude, m.longitude, m.latitude  # for geometry CASE WHEN and ST_MakePoint
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
                    """SELECT latest_sync_date FROM sync_state WHERE "boxId" = %s;""",
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
                    INSERT INTO sync_state ("boxId", latest_sync_date, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT ("boxId") 
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
