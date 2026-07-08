-- Migration 003: Create statistics table (required by the Statistics analysis process)
-- This table stores tour-level cycling statistics with a convex hull geometry (Polygon).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

CREATE TABLE IF NOT EXISTS statistics (
    tag TEXT PRIMARY KEY,
    geometry GEOMETRY(Polygon, 4326),
    statistics TEXT,
    "updatedAt" TIMESTAMP
);
