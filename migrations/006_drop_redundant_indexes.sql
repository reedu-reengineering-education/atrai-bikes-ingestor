-- Migration 006: drop redundant indexes on the measurement tables
-- The UNIQUE("boxId", "createdAt") constraint already creates an index that
-- serves lookups by boxId and by (boxId, createdAt). The separate indexes
-- duplicated it, took ~150 MB on osem_bike_data and slowed down every upsert.

DROP INDEX IF EXISTS idx_osem_bike_data_boxid;
DROP INDEX IF EXISTS idx_osem_bike_data_boxid_timestamp;

DROP INDEX IF EXISTS idx_osem_home_data_heilbronn_boxid;
DROP INDEX IF EXISTS idx_osem_home_data_heilbronn_boxid_timestamp;
