# Multi-Phenomenon Measurement Approach

## Overview

The system now uses a sophisticated **upsert approach** to store multiple phenomena (temperature, humidity, PM values, etc.) in a single measurement record per (boxid, timestamp) combination.

## Problem Solved

Previously, each sensor reading created a separate database row, even if multiple sensors recorded data at the same timestamp. This resulted in:
- Data fragmentation across multiple rows
- Difficulty querying all phenomena for a specific measurement
- Inefficient storage and indexing

## Solution

### 1. Timestamp-Based Aggregation

The `sync_coordinator.py` now aggregates sensor readings by timestamp:

```python
measurements_by_timestamp = {}

for sensor in sensors:
    for data_point in parsed_data:
        timestamp = data_point['timestamp']
        
        # Initialize or update measurement for this timestamp
        if timestamp not in measurements_by_timestamp:
            measurements_by_timestamp[timestamp] = {
                'boxid': box.id,
                'timestamp': timestamp,
                # ... other fields
            }
        
        # Add this phenomenon to the measurement
        measurements_by_timestamp[timestamp][column_name] = data_point['value']
```

### 2. Upsert Database Logic

The `database.py` uses PostgreSQL's `ON CONFLICT DO UPDATE` to merge phenomena:

```sql
INSERT INTO measurements (
    boxid, timestamp, temperature, humidity, pm2_5, ...
) VALUES (
    %s, %s, %s, %s, %s, ...
)
ON CONFLICT (boxid, timestamp) DO UPDATE SET
    temperature = COALESCE(EXCLUDED.temperature, measurements.temperature),
    humidity = COALESCE(EXCLUDED.humidity, measurements.humidity),
    pm2_5 = COALESCE(EXCLUDED.pm2_5, measurements.pm2_5),
    ...
```

The `COALESCE` function ensures that:
- New non-null values update existing nulls
- Existing non-null values are preserved if new value is null
- New non-null values override existing non-null values

## Benefits

1. **Efficient Storage**: One row per measurement instead of one row per phenomenon
2. **Simplified Queries**: All phenomena for a timestamp are in the same row
3. **Handles Out-of-Order Data**: Upsert gracefully handles sensors reporting at different times
4. **GPS Coordinate Merging**: Latest non-null GPS coordinates are preserved
5. **Idempotent**: Re-running sync jobs safely updates existing data

## Example

### Before (Multiple Rows)
```
| boxid | timestamp           | temperature | humidity | pm2_5 |
|-------|---------------------|-------------|----------|-------|
| box1  | 2024-01-01 12:00:00 | 20.5        | NULL     | NULL  |
| box1  | 2024-01-01 12:00:00 | NULL        | 65.0     | NULL  |
| box1  | 2024-01-01 12:00:00 | NULL        | NULL     | 12.3  |
```

### After (Single Row)
```
| boxid | timestamp           | temperature | humidity | pm2_5 |
|-------|---------------------|-------------|----------|-------|
| box1  | 2024-01-01 12:00:00 | 20.5        | 65.0     | 12.3  |
```

## Migration

No schema changes are required. The existing `UNIQUE(boxid, timestamp)` constraint already supports the upsert behavior.

See `migrations/002_upsert_multiple_phenomena.sql` for details.

## Testing

To verify the upsert behavior:

1. Run a sync job for a box with multiple sensors
2. Query the database to confirm one row per timestamp
3. Re-run the same sync job to verify idempotency

```sql
-- Check measurements for a specific box and date
SELECT 
    timestamp,
    temperature,
    humidity,
    pm2_5,
    longitude,
    latitude
FROM measurements
WHERE boxid = 'your_box_id'
    AND timestamp::date = '2024-01-01'
ORDER BY timestamp;
```
