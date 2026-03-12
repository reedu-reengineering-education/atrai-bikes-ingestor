#!/bin/sh
# Generate crontab from environment and start supercronic

SYNC_SCHEDULE="${SYNC_SCHEDULE:-0 3 * * *}"

echo "# Sensor data sync cron schedule" > /app/crontab
echo "# Schedule: $SYNC_SCHEDULE" >> /app/crontab
echo "$SYNC_SCHEDULE /usr/bin/sh -c 'cd /app && /root/.local/bin/uv run python -m src.scheduler'" >> /app/crontab

echo "Starting supercronic with schedule: $SYNC_SCHEDULE"
exec supercronic /app/crontab
