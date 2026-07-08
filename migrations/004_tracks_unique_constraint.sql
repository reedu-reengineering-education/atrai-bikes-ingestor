-- Migration 004: deduplicate tracks and add unique constraint
-- Remove duplicate tracks keeping the earliest (lowest id) per box+time window,
-- then enforce uniqueness to prevent future duplicates.

DELETE FROM tracks
WHERE id NOT IN (
    SELECT MIN(id)
    FROM tracks
    GROUP BY "boxId", "startTime", "endTime"
);

DELETE FROM track_points
WHERE track_id NOT IN (SELECT id FROM tracks);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tracks_box_time_unique'
    ) THEN
        ALTER TABLE tracks
            ADD CONSTRAINT tracks_box_time_unique
            UNIQUE ("boxId", "startTime", "endTime");
    END IF;
END $$;
