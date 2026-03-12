-- Migration: Rename columns to match OpenSenseMapToolbox format
-- This migration updates existing tables to use column names compatible with pygeoapi processes
-- Date: 2026-03-12
--
-- BEFORE: sensor-data-sync internal naming (lowercase, underscores)
-- AFTER:  OpenSenseMapToolbox naming (mixed case, spaces, human-readable)

-- ============================================
-- Rename osem_bike_data columns
-- ============================================

-- Rename primary key column
ALTER TABLE osem_bike_data RENAME COLUMN id TO index;

-- Rename metadata columns
ALTER TABLE osem_bike_data RENAME COLUMN boxid TO "boxId";
ALTER TABLE osem_bike_data RENAME COLUMN boxname TO "boxName";
ALTER TABLE osem_bike_data RENAME COLUMN grouptags TO "groupTags";
ALTER TABLE osem_bike_data RENAME COLUMN timestamp TO "createdAt";

-- Rename environmental sensor columns
ALTER TABLE osem_bike_data RENAME COLUMN temperature TO "Temperature";
ALTER TABLE osem_bike_data RENAME COLUMN humidity TO "Rel. Humidity";
ALTER TABLE osem_bike_data RENAME COLUMN pm1 TO "Finedust PM1";
ALTER TABLE osem_bike_data RENAME COLUMN pm2_5 TO "Finedust PM2.5";
ALTER TABLE osem_bike_data RENAME COLUMN pm4 TO "Finedust PM4";
ALTER TABLE osem_bike_data RENAME COLUMN pm10 TO "Finedust PM10";

-- Rename distance sensor columns
ALTER TABLE osem_bike_data RENAME COLUMN overtaking_distance TO "Overtaking Distance";
ALTER TABLE osem_bike_data RENAME COLUMN distance_right TO "Distance Right";
ALTER TABLE osem_bike_data RENAME COLUMN overtaking_maneuvre TO "Overtaking Manoeuvre";

-- Rename surface classification columns
ALTER TABLE osem_bike_data RENAME COLUMN standing TO "Standing";
ALTER TABLE osem_bike_data RENAME COLUMN asphalt TO "Surface Asphalt";
ALTER TABLE osem_bike_data RENAME COLUMN compacted TO "Surface Compacted";
ALTER TABLE osem_bike_data RENAME COLUMN paving TO "Surface Paving";
ALTER TABLE osem_bike_data RENAME COLUMN sett TO "Surface Sett";

-- Rename speed column
ALTER TABLE osem_bike_data RENAME COLUMN speed TO "Speed";

-- Rename geometry column
ALTER TABLE osem_bike_data RENAME COLUMN geom TO geometry;

-- ============================================
-- Update sync_state table
-- ============================================

ALTER TABLE sync_state RENAME COLUMN boxid TO "boxId";

-- ============================================
-- Recreate indexes with new column names
-- ============================================

-- Drop old indexes (they reference old column names)
DROP INDEX IF EXISTS idx_osem_bike_data_boxid;
DROP INDEX IF EXISTS idx_osem_bike_data_timestamp;
DROP INDEX IF EXISTS idx_osem_bike_data_boxid_timestamp;
DROP INDEX IF EXISTS idx_osem_bike_data_geom;

-- Create new indexes with updated column names
CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid 
ON osem_bike_data("boxId");

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_timestamp 
ON osem_bike_data("createdAt");

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_boxid_timestamp 
ON osem_bike_data("boxId", "createdAt");

CREATE INDEX IF NOT EXISTS idx_osem_bike_data_geom 
ON osem_bike_data USING GIST (geometry);

-- ============================================
-- Update unique constraint
-- ============================================

-- Drop old constraint and recreate with new column names
ALTER TABLE osem_bike_data DROP CONSTRAINT IF EXISTS osem_bike_data_boxid_timestamp_key;
ALTER TABLE osem_bike_data ADD CONSTRAINT osem_bike_data_boxid_createdat_key UNIQUE ("boxId", "createdAt");
