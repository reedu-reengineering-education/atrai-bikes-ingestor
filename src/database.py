"""
Database Manager for PostGIS

This module provides functionality to manage database connections and operations
for storing sensor measurements in a PostGIS database.
"""

import re
from typing import List, Optional
from datetime import date
import psycopg2
from psycopg2 import sql
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

    def _create_indexes(self, cursor, table_name: str):
        """
        Create the createdAt/geometry indexes for a measurements table.

        No separate boxId or (boxId, createdAt) index: the UNIQUE("boxId",
        "createdAt") constraint's index already covers both, and extra indexes
        only slow down the upserts (see migrations/006_drop_redundant_indexes.sql).
        """
        table = sql.Identifier(table_name)
        idx_prefix = re.sub(r'[^A-Za-z0-9_]', '_', table_name)

        cursor.execute(sql.SQL(
            "CREATE INDEX IF NOT EXISTS {idx} ON {table}(\"createdAt\");"
        ).format(idx=sql.Identifier(f"idx_{idx_prefix}_timestamp"), table=table))

        cursor.execute(sql.SQL(
            "CREATE INDEX IF NOT EXISTS {idx} ON {table} USING GIST (geometry);"
        ).format(idx=sql.Identifier(f"idx_{idx_prefix}_geom"), table=table))

    def create_schema(self, table_name: str = "osem_bike_data"):
        """
        Create a database table and indexes if they don't exist.

        Creates:
            - <table_name> table with all sensor columns
            - indexes on boxId and createdAt columns

        NOTE: Column names match OpenSenseMapToolbox output format for
        compatibility with existing pygeoapi processes.

        For senseBox:home / weather-station devices with a different phenomenon
        set, see create_home_schema() instead.
        """
        table = sql.Identifier(table_name)

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Create table with OpenSenseMapToolbox-compatible column names
                cursor.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {table} (
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
                """).format(table=table))

                self._create_indexes(cursor, table_name)

                conn.commit()
        finally:
            self.pool.putconn(conn)

    def create_home_schema(self, table_name: str = "osem_home_data_heilbronn"):
        """
        Create the table and indexes for senseBox:home / weather-station devices.

        These devices report a different (and, per device, differently-named/
        localized) set of phenomena than the bike sensors — temperature,
        humidity, pressure, illuminance, UV, wind, rain, etc. rather than
        overtaking distance, surface type, speed. Kept as its own table/schema
        so it doesn't need to shoehorn into the bike column layout, and so the
        bike sync (create_schema/insert_measurements) is entirely unaffected.
        """
        table = sql.Identifier(table_name)

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {table} (
                        index SERIAL PRIMARY KEY,
                        "boxId" VARCHAR(255) NOT NULL,
                        "boxName" VARCHAR(255) NOT NULL,
                        "groupTags" TEXT,
                        "createdAt" TIMESTAMP NOT NULL,
                        longitude DOUBLE PRECISION,
                        latitude DOUBLE PRECISION,
                        "Temperature" DOUBLE PRECISION,
                        "Rel. Humidity" DOUBLE PRECISION,
                        "Pressure" DOUBLE PRECISION,
                        "Illuminance" DOUBLE PRECISION,
                        "UV Intensity" DOUBLE PRECISION,
                        "UV Index" DOUBLE PRECISION,
                        "Finedust PM1" DOUBLE PRECISION,
                        "Finedust PM2.5" DOUBLE PRECISION,
                        "Finedust PM4" DOUBLE PRECISION,
                        "Finedust PM10" DOUBLE PRECISION,
                        "Wind Speed" DOUBLE PRECISION,
                        "Wind Gust" DOUBLE PRECISION,
                        "Wind Direction" DOUBLE PRECISION,
                        "Rain Rate" DOUBLE PRECISION,
                        "Dewpoint" DOUBLE PRECISION,
                        "Solar Radiation" DOUBLE PRECISION,
                        "Cloud Base" DOUBLE PRECISION,
                        geometry geometry(Point, 4326),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE("boxId", "createdAt")
                    );
                """).format(table=table))

                # If the table already existed (e.g. created by an earlier version
                # that reused the bike column layout), make sure the home-specific
                # columns are present.
                for column in (
                    "Pressure", "Illuminance", "UV Intensity", "UV Index",
                    "Wind Speed", "Wind Gust", "Wind Direction", "Rain Rate",
                    "Dewpoint", "Solar Radiation", "Cloud Base",
                ):
                    cursor.execute(sql.SQL(
                        "ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} DOUBLE PRECISION;"
                    ).format(table=table, column=sql.Identifier(column)))

                # ...and drop the bike-only columns it may have inherited from
                # that earlier version — they don't apply to home devices and
                # otherwise show up (always NULL) in the /collections API.
                for column in (
                    "Overtaking Distance", "Overtaking Manoeuvre", "Standing",
                    "Surface Asphalt", "Surface Compacted", "Surface Paving",
                    "Surface Sett", "Speed", "Distance Right",
                ):
                    cursor.execute(sql.SQL(
                        "ALTER TABLE {table} DROP COLUMN IF EXISTS {column};"
                    ).format(table=table, column=sql.Identifier(column)))

                self._create_indexes(cursor, table_name)

                conn.commit()
        finally:
            self.pool.putconn(conn)

    def insert_measurements(self, measurements: List, table_name: str = "osem_bike_data") -> int:
        """
        Insert or update measurements into the database.

        Uses ON CONFLICT DO UPDATE to merge multiple phenomena into the same row.
        This allows multiple sensor readings (temperature, humidity, etc.) to be
        combined into a single measurement record per (boxId, createdAt).

        Args:
            measurements: List of Measurement objects
            table_name: Table to insert into (default: osem_bike_data)

        Returns:
            Number of rows inserted or updated
        """
        if not measurements:
            return 0

        table = sql.Identifier(table_name)

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                # Prepare the INSERT statement with ON CONFLICT DO UPDATE
                # This will merge multiple phenomena into the same row
                # Column names match OpenSenseMapToolbox output format
                insert_query = sql.SQL("""
                    INSERT INTO {table} (
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
                        "boxName" = COALESCE(EXCLUDED."boxName", {table}."boxName"),
                        "groupTags" = COALESCE(EXCLUDED."groupTags", {table}."groupTags"),
                        longitude = COALESCE(EXCLUDED.longitude, {table}.longitude),
                        latitude = COALESCE(EXCLUDED.latitude, {table}.latitude),
                        "Temperature" = COALESCE(EXCLUDED."Temperature", {table}."Temperature"),
                        "Rel. Humidity" = COALESCE(EXCLUDED."Rel. Humidity", {table}."Rel. Humidity"),
                        "Finedust PM1" = COALESCE(EXCLUDED."Finedust PM1", {table}."Finedust PM1"),
                        "Finedust PM2.5" = COALESCE(EXCLUDED."Finedust PM2.5", {table}."Finedust PM2.5"),
                        "Finedust PM4" = COALESCE(EXCLUDED."Finedust PM4", {table}."Finedust PM4"),
                        "Finedust PM10" = COALESCE(EXCLUDED."Finedust PM10", {table}."Finedust PM10"),
                        "Overtaking Distance" = COALESCE(EXCLUDED."Overtaking Distance", {table}."Overtaking Distance"),
                        "Overtaking Manoeuvre" = COALESCE(EXCLUDED."Overtaking Manoeuvre", {table}."Overtaking Manoeuvre"),
                        "Standing" = COALESCE(EXCLUDED."Standing", {table}."Standing"),
                        "Surface Asphalt" = COALESCE(EXCLUDED."Surface Asphalt", {table}."Surface Asphalt"),
                        "Surface Compacted" = COALESCE(EXCLUDED."Surface Compacted", {table}."Surface Compacted"),
                        "Surface Paving" = COALESCE(EXCLUDED."Surface Paving", {table}."Surface Paving"),
                        "Surface Sett" = COALESCE(EXCLUDED."Surface Sett", {table}."Surface Sett"),
                        "Speed" = COALESCE(EXCLUDED."Speed", {table}."Speed"),
                        "Distance Right" = COALESCE(EXCLUDED."Distance Right", {table}."Distance Right"),
                        geometry = COALESCE(EXCLUDED.geometry, {table}.geometry);
                """).format(table=table)

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

    def insert_home_measurements(self, measurements: List, table_name: str = "osem_home_data_heilbronn") -> int:
        """
        Insert or update senseBox:home measurements into the database.

        Mirrors insert_measurements() but targets the home-device column set
        (see create_home_schema()) instead of the bike sensor columns.

        Args:
            measurements: List of Measurement objects
            table_name: Table to insert into (default: osem_home_data_heilbronn)

        Returns:
            Number of rows inserted or updated
        """
        if not measurements:
            return 0

        table = sql.Identifier(table_name)

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                insert_query = sql.SQL("""
                    INSERT INTO {table} (
                        "boxId", "boxName", "groupTags", "createdAt", longitude, latitude,
                        "Temperature", "Rel. Humidity", "Pressure", "Illuminance", "UV Intensity", "UV Index",
                        "Finedust PM1", "Finedust PM2.5", "Finedust PM4", "Finedust PM10",
                        "Wind Speed", "Wind Gust", "Wind Direction", "Rain Rate", "Dewpoint",
                        "Solar Radiation", "Cloud Base", geometry
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NOT NULL AND %s IS NOT NULL
                             THEN ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                             ELSE NULL END
                    )
                    ON CONFLICT ("boxId", "createdAt") DO UPDATE SET
                        "boxName" = COALESCE(EXCLUDED."boxName", {table}."boxName"),
                        "groupTags" = COALESCE(EXCLUDED."groupTags", {table}."groupTags"),
                        longitude = COALESCE(EXCLUDED.longitude, {table}.longitude),
                        latitude = COALESCE(EXCLUDED.latitude, {table}.latitude),
                        "Temperature" = COALESCE(EXCLUDED."Temperature", {table}."Temperature"),
                        "Rel. Humidity" = COALESCE(EXCLUDED."Rel. Humidity", {table}."Rel. Humidity"),
                        "Pressure" = COALESCE(EXCLUDED."Pressure", {table}."Pressure"),
                        "Illuminance" = COALESCE(EXCLUDED."Illuminance", {table}."Illuminance"),
                        "UV Intensity" = COALESCE(EXCLUDED."UV Intensity", {table}."UV Intensity"),
                        "UV Index" = COALESCE(EXCLUDED."UV Index", {table}."UV Index"),
                        "Finedust PM1" = COALESCE(EXCLUDED."Finedust PM1", {table}."Finedust PM1"),
                        "Finedust PM2.5" = COALESCE(EXCLUDED."Finedust PM2.5", {table}."Finedust PM2.5"),
                        "Finedust PM4" = COALESCE(EXCLUDED."Finedust PM4", {table}."Finedust PM4"),
                        "Finedust PM10" = COALESCE(EXCLUDED."Finedust PM10", {table}."Finedust PM10"),
                        "Wind Speed" = COALESCE(EXCLUDED."Wind Speed", {table}."Wind Speed"),
                        "Wind Gust" = COALESCE(EXCLUDED."Wind Gust", {table}."Wind Gust"),
                        "Wind Direction" = COALESCE(EXCLUDED."Wind Direction", {table}."Wind Direction"),
                        "Rain Rate" = COALESCE(EXCLUDED."Rain Rate", {table}."Rain Rate"),
                        "Dewpoint" = COALESCE(EXCLUDED."Dewpoint", {table}."Dewpoint"),
                        "Solar Radiation" = COALESCE(EXCLUDED."Solar Radiation", {table}."Solar Radiation"),
                        "Cloud Base" = COALESCE(EXCLUDED."Cloud Base", {table}."Cloud Base"),
                        geometry = COALESCE(EXCLUDED.geometry, {table}.geometry);
                """).format(table=table)

                data = [
                    (
                        m.boxid, m.boxname, m.grouptags, m.timestamp, m.longitude, m.latitude,
                        m.temperature, m.humidity, m.pressure, m.illuminance, m.uv, m.uv_index,
                        m.pm1, m.pm2_5, m.pm4, m.pm10,
                        m.wind_speed, m.wind_gust, m.wind_direction, m.rain_rate, m.dewpoint,
                        m.solar_radiation, m.cloud_base,
                        m.longitude, m.latitude, m.longitude, m.latitude  # for geometry CASE WHEN and ST_MakePoint
                    )
                    for m in measurements
                ]

                execute_batch(cursor, insert_query, data)

                rows_affected = cursor.rowcount

                conn.commit()

                return rows_affected
        except Exception as e:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

    def get_latest_sync_date(self, box_id: str, table_name: str = "osem_bike_data") -> Optional[date]:
        """
        Get the date to resume syncing from for a box.

        Derived from the actual latest stored measurement rather than a
        separate bookkeeping table, so it can never drift ahead of what was
        really ingested (e.g. a day whose archive wasn't published yet, or
        an insert that silently found nothing to write).

        Args:
            box_id: The box ID
            table_name: Table to query (default: osem_bike_data)

        Returns:
            Date of the latest stored measurement, or None if no data exists
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("""SELECT MAX("createdAt")::date FROM {table} WHERE "boxId" = %s;""")
                    .format(table=sql.Identifier(table_name)),
                    (box_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        finally:
            self.pool.putconn(conn)

    def analyze(self, table_names: List[str]):
        """
        Refresh planner statistics for the given tables.

        Postgres loses its statistics after a crash and autovacuum only
        recomputes them once enough rows change, so without this the planner
        can be left estimating a few thousand rows for a table of millions.
        """
        conn = self.pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cursor:
                for table_name in table_names:
                    cursor.execute(sql.SQL("ANALYZE {table};").format(table=sql.Identifier(table_name)))
        finally:
            conn.autocommit = False
            self.pool.putconn(conn)

    def close(self):
        """Close all database connections in the pool."""
        if self.pool:
            self.pool.closeall()
