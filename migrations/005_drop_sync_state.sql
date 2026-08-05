-- ============================================
-- Drop sync state table
-- ============================================
-- The sync resume point is now derived from the latest stored measurement
-- (MAX("createdAt") in osem_bike_data, see DatabaseManager.get_latest_sync_date),
-- so the separate bookkeeping table is no longer read or written by anything.

DROP TABLE IF EXISTS sync_state;
