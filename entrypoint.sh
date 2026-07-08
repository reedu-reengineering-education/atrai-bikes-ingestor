#!/bin/bash
# App entrypoint: wait for the database, run migrations, then start the process
# passed as arguments (CMD from Dockerfile / docker-compose command:).
set -e

echo "Waiting for database..."
until python - <<'PY' 2>/dev/null
import os, psycopg2
psycopg2.connect(os.environ["DATABASE_URL"]).close()
PY
do
  sleep 2
done
echo "Database ready."

echo "Running migrations..."
python run_migration.py

echo "Starting: $*"
exec "$@"
