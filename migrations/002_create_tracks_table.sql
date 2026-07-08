-- Track Analysis Tables
-- Stores processed tracks with statistics and track points

CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================
-- Tracks table: aggregated track statistics
-- ============================================
CREATE TABLE IF NOT EXISTS tracks (
    id SERIAL PRIMARY KEY,
    "boxId" VARCHAR(255) NOT NULL,
    "boxName" VARCHAR(255) NOT NULL,
    "groupTags" TEXT,
    
    -- Track temporal bounds
    "startTime" TIMESTAMP NOT NULL,
    "endTime" TIMESTAMP NOT NULL,
    
    -- Track statistics
    "duration_seconds" DOUBLE PRECISION,        -- Total duration in seconds
    "distance_meters" DOUBLE PRECISION,         -- Total distance in meters
    "num_points" INTEGER,                       -- Number of GPS points
    "avg_speed_ms" DOUBLE PRECISION,            -- Average speed in m/s
    "max_speed_ms" DOUBLE PRECISION,            -- Max speed in m/s
    
    -- Spatial data
    "linestring_geometry" GEOMETRY(LINESTRING, 4326),  -- Track as linestring
    "start_geometry" GEOMETRY(POINT, 4326),            -- Start point
    "end_geometry" GEOMETRY(POINT, 4326),              -- End point
    
    -- Aggregated sensor statistics (avg values during track)
    "avg_temperature" DOUBLE PRECISION,
    "avg_humidity" DOUBLE PRECISION,
    "avg_pm25" DOUBLE PRECISION,
    "avg_pm10" DOUBLE PRECISION,
    "avg_overtaking_distance" DOUBLE PRECISION,
    "avg_distance_right" DOUBLE PRECISION,
    
    -- Metadata
    "created_at" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "processed_at" TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tracks_boxid ON tracks("boxId");
CREATE INDEX IF NOT EXISTS idx_tracks_starttime ON tracks("startTime");
CREATE INDEX IF NOT EXISTS idx_tracks_geometry ON tracks USING GIST ("linestring_geometry");

-- ============================================
-- Track points table: cleaned GPS points per track
-- ============================================
CREATE TABLE IF NOT EXISTS track_points (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    "boxId" VARCHAR(255) NOT NULL,
    
    -- Temporal
    "timestamp" TIMESTAMP NOT NULL,
    "sequence" INTEGER,  -- Order within track
    
    -- GPS
    longitude DOUBLE PRECISION NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(POINT, 4326),
    
    -- Speed
    "speed_ms" DOUBLE PRECISION,  -- m/s
    
    -- Environmental sensors
    "temperature" DOUBLE PRECISION,
    "humidity" DOUBLE PRECISION,
    "pm25" DOUBLE PRECISION,
    "pm10" DOUBLE PRECISION,
    
    -- Distance sensors
    "overtaking_distance" DOUBLE PRECISION,
    "distance_right" DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_track_points_track_id ON track_points(track_id);
CREATE INDEX IF NOT EXISTS idx_track_points_boxid ON track_points("boxId");
CREATE INDEX IF NOT EXISTS idx_track_points_geometry ON track_points USING GIST (geometry);
