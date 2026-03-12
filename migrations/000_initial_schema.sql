-- Initial Schema Migration for OpenSenseMap Bike Data Sync
-- Creates all tables and indexes for a fresh production deployment
-- Date: 2026-03-12

-- Enable PostGIS extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================
-- Main data table: osem_bike_data
-- ============================================
-- Stores sensor measurements from OpenSenseMap bike boxes
-- One row per (boxid, timestamp) with all sensor values

CREATE TABLE IF NOT EXISTS osem_bike_data (
    id SERIAL PRIMARY KEY,
    boxid VARCHAR(255) NOT NULL,
    boxname VARCHAR(255) NOT NULL,
    grouptags TEXT,
    timestamp TIMESTAMP NOT NULL,
    
    -- GPS coordinates
    longitude DOUBLE PRECISION,
    latitude DOUBLE PRECISION,
    
    -- Environmental sensors
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    pm1 DOUBLE PRECISION,
    pm2_5 DOUBLE PRECISION,
    pm4 DOUBLE PRECISION,
    pm10 DOUBLE PRECISION,
    
    -- Distance sensors
    overtaking_distance DOUBLE PRECISION,  -- Distance left (cm)
    distance_right DOUBLE PRECISION,        -- Distance right (cm)
    overtaking_maneuvre INTEGER,            -- Overtaking manoeuvre detection (%)
    
    -- Surface classification
    standing INTEGER,
    asphalt INTEGER,
    compacted INTEGER,
    paving INTEGER,
    sett INTEGER,
    
    -- GPS speed
    speed DOUBLE PRECISION,  -- m/s
    
    -- PostGIS geometry for tile serving
    geom geometry(Point, 4326),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint for upsert behavior
    UNIQUE(boxid, timestamp)
);

-- Column comments
COMMENT ON TABLE osem_bike_data IS 'Sensor measurements from OpenSenseMap bike boxes';
COMMENT ON COLUMN osem_bike_data.longitude IS 'GPS longitude in decimal degrees';
COMMENT ON COLUMN osem_bike_data.latitude IS 'GPS latitude in decimal degrees';
COMMENT ON COLUMN osem_bike_data.overtaking_distance IS 'Distance to objects on the left in cm';
COMMENT ON COLUMN osem_bike_data.distance_right IS 'Distance to objects on the right in cm';
COMMENT ON COLUMN osem_bike_data.speed IS 'GPS speed in m/s';
COMMENT ON COLUMN osem_bike_data.geom IS 'PostGIS point geometry for spatial queries and tile serving';

-- ============================================
-- Indexes for osem_bike_data
-- ============================================

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid 
ON osem_bike_data(boxid);

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_timestamp 
ON osem_bike_data(timestamp);

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid_timestamp 
ON osem_bike_data(boxid, timestamp);

-- Spatial index for PostGIS geometry (used by Martin tile server)
CREATE INDEX IF NOT EXISTS idx_osem_bike_data_geom 
ON osem_bike_data USING GIST (geom);

-- ============================================
-- Sync state table
-- ============================================
-- Tracks the last sync date for each box to enable incremental sync

CREATE TABLE IF NOT EXISTS sync_state (
    boxid VARCHAR(255) PRIMARY KEY,
    latest_sync_date DATE NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE sync_state IS 'Tracks sync progress for incremental data fetching';
