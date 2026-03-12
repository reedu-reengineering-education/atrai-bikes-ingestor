# Database Migration Guide

This guide explains how to manage database schema changes for the sensor data synchronization system.

## Overview

Database migrations are SQL scripts stored in the `migrations/` directory that modify the database schema. Each migration file is numbered sequentially (e.g., `001_`, `002_`, etc.) to ensure they run in the correct order.

## Running Migrations

### Run All Migrations

To apply all pending migrations:

```bash
uv run python run_migration.py
```

This will execute all `.sql` files in the `migrations/` directory in alphabetical order.

### Run a Specific Migration

To apply a single migration file:

```bash
uv run python run_migration.py migrations/001_add_gps_columns.sql
```

## Available Migrations

### 001_add_gps_columns.sql

**Purpose:** Adds GPS coordinate columns to the measurements table

**Changes:**
- Adds `longitude` column (DOUBLE PRECISION)
- Adds `latitude` column (DOUBLE PRECISION)
- Creates index on GPS coordinates for spatial queries
- Adds column comments for documentation

**When to apply:** Required for systems that need to store GPS coordinates from mobile sensor boxes.

**Safe to re-run:** Yes (uses `IF NOT EXISTS` clauses)

## Creating New Migrations

When you need to modify the database schema:

1. **Create a new migration file** in the `migrations/` directory:
   ```
   migrations/00X_description.sql
   ```
   Use the next sequential number (e.g., `002_`, `003_`, etc.)

2. **Write idempotent SQL** that can be safely re-run:
   ```sql
   -- Good: Uses IF NOT EXISTS
   ALTER TABLE measurements 
   ADD COLUMN IF NOT EXISTS new_column VARCHAR(255);
   
   -- Bad: Will fail if column exists
   ALTER TABLE measurements 
   ADD COLUMN new_column VARCHAR(255);
   ```

3. **Test the migration** on a development database first:
   ```bash
   uv run python run_migration.py migrations/00X_description.sql
   ```

4. **Document the migration** in this guide

## Migration Best Practices

1. **Use IF NOT EXISTS / IF EXISTS clauses** to make migrations idempotent
2. **Add indexes** for columns that will be frequently queried
3. **Add comments** to document column purposes
4. **Test on development** before applying to production
5. **Backup the database** before running migrations in production
6. **Keep migrations small** - one logical change per migration
7. **Never modify existing migrations** - create a new one instead

## Rollback Strategy

If a migration causes issues:

1. **Identify the problem** by checking logs and database state
2. **Create a rollback migration** that reverses the changes
3. **Test the rollback** on a development database
4. **Apply the rollback** to production if needed

Example rollback for `001_add_gps_columns.sql`:

```sql
-- Rollback: Remove GPS columns
ALTER TABLE measurements DROP COLUMN IF EXISTS longitude;
ALTER TABLE measurements DROP COLUMN IF EXISTS latitude;
DROP INDEX IF EXISTS idx_measurements_location;
```

## Production Deployment

When deploying to production:

1. **Backup the database**:
   ```bash
   pg_dump -U postgres sensor_data > backup_$(date +%Y%m%d_%H%M%S).sql
   ```

2. **Run migrations**:
   ```bash
   uv run python run_migration.py
   ```

3. **Verify the changes**:
   ```bash
   psql -U postgres -d sensor_data -c "\d measurements"
   ```

4. **Test the application** to ensure it works with the new schema

## Troubleshooting

### Migration fails with "relation does not exist"

The database tables haven't been created yet. Run the application once to create the initial schema, then run migrations.

### Migration fails with "column already exists"

The migration has already been applied. This is safe to ignore if using `IF NOT EXISTS` clauses.

### Migration fails with permission error

Ensure the database user has sufficient privileges:
```sql
GRANT ALL PRIVILEGES ON DATABASE sensor_data TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

## Docker Compose

When using Docker Compose, migrations can be run inside the container:

```bash
# Development
docker-compose -f docker-compose.dev.yml exec sync-app uv run python run_migration.py

# Production
docker-compose -f docker-compose.prod.yml exec sync-app uv run python run_migration.py
```

Or add migrations to the container startup script to run automatically.
