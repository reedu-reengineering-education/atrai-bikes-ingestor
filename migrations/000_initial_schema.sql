-- Initial Schema Migration for OpenSenseMap Bike Data Sync
-- Creates all tables and indexes for a fresh production deployment
-- Date: 2026-03-12
-- 
-- NOTE: Column names match OpenSenseMapToolbox output format for compatibility
-- with existing pygeoapi processes

-- Enable PostGIS extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================
-- Main data table: osem_bike_data
-- ============================================
-- Stores sensor measurements from OpenSenseMap bike boxes
-- One row per (boxId, createdAt) with all sensor values
-- Column names match OpenSenseMapToolbox output format

CREATE TABLE IF NOT EXISTS osem_bike_data (
    index SERIAL PRIMARY KEY,
    "boxId" VARCHAR(255) NOT NULL,
    "boxName" VARCHAR(255) NOT NULL,
    "groupTags" TEXT,
    "createdAt" TIMESTAMP NOT NULL,
    
    -- GPS coordinates
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    
    -- Environmental sensors
    "Temperature" DOUBLE PRECISION,
    "Rel. Humidity" DOUBLE PRECISION,
    "Finedust PM1" DOUBLE PRECISION,
    "Finedust PM2.5" DOUBLE PRECISION,
    "Finedust PM4" DOUBLE PRECISION,
    "Finedust PM10" DOUBLE PRECISION,
    
    -- Distance sensors
    "Overtaking Distance" DOUBLE PRECISION,  -- Distance left (cm)
    "Distance Right" DOUBLE PRECISION,        -- Distance right (cm)
    "Overtaking Manoeuvre" INTEGER,           -- Overtaking manoeuvre detection (%)
    
    -- Surface classification
    "Standing" INTEGER,
    "Surface Asphalt" INTEGER,
    "Surface Compacted" INTEGER,
    "Surface Paving" INTEGER,
    "Surface Sett" INTEGER,
    
    -- GPS speed
    "Speed" DOUBLE PRECISION,  -- m/s
    
    -- PostGIS geometry for tile serving
    geometry geometry(Point, 4326),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint for upsert behavior
    UNIQUE("boxId", "createdAt")
);

-- Column comments
COMMENT ON TABLE osem_bike_data IS 'Sensor measurements from OpenSenseMap bike boxes';
COMMENT ON COLUMN osem_bike_data.longitude IS 'GPS longitude in decimal degrees';
COMMENT ON COLUMN osem_bike_data.latitude IS 'GPS latitude in decimal degrees';
COMMENT ON COLUMN osem_bike_data."Overtaking Distance" IS 'Distance to objects on the left in cm';
COMMENT ON COLUMN osem_bike_data."Distance Right" IS 'Distance to objects on the right in cm';
COMMENT ON COLUMN osem_bike_data."Speed" IS 'GPS speed in m/s';
COMMENT ON COLUMN osem_bike_data.geometry IS 'PostGIS point geometry for spatial queries and tile serving';

-- ============================================
-- Indexes for osem_bike_data
-- ============================================

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid 
ON osem_bike_data("boxId");

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_timestamp 
ON osem_bike_data("createdAt");

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid_timestamp 
ON osem_bike_data("boxId", "createdAt");

-- Spatial index for PostGIS geometry (used by Martin tile server)
CREATE INDEX IF NOT EXISTS idx_osem_bike_data_geom 
ON osem_bike_data USING GIST (geometry);

-- ============================================
-- Sync state table
-- ============================================
-- Tracks the last sync date for each box to enable incremental sync

CREATE TABLE IF NOT EXISTS sync_state (
    "boxId" VARCHAR(255) PRIMARY KEY,
    latest_sync_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE sync_state IS 'Tracks sync progress for incremental data fetching';
