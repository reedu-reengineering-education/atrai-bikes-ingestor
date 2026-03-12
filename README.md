# Sensor Data Synchronization System

A Python application that periodically fetches environmental sensor data from OpenSenseMap archives and stores it in a PostGIS database. The system implements incremental synchronization to avoid reprocessing historical data.

## Features

- Fetches sensor box metadata from OpenSenseMap API
- Downloads historical sensor data from OpenSenseMap archives
- Parses CSV sensor data and JSON metadata
- **Aggregates multiple phenomena** (temperature, humidity, PM values, etc.) into single measurement records
- **Upsert logic** merges sensor readings by timestamp and geoposition
- Stores measurements in PostGIS database with intelligent duplicate handling
- Performs incremental synchronization based on last sync date
- Handles data gaps and missing archive files gracefully
- Can be scheduled via cron for automated sync jobs

## Project Structure

```
sensor-data-sync/
├── src/
│   ├── __init__.py
│   ├── api_client.py       # OpenSenseMap API and archive client
│   ├── parser.py            # CSV and JSON data parser
│   ├── database.py          # PostGIS database manager
│   ├── sync_coordinator.py  # Synchronization workflow orchestrator
│   └── scheduler.py         # Main sync job execution script
├── .env.example             # Example environment configuration
├── pyproject.toml           # Python dependencies and metadata
└── README.md                # This file
```

## Requirements

- Python 3.9 or higher
- PostgreSQL with PostGIS extension
- uv package manager

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd sensor-data-sync
```

2. Install dependencies using uv:
```bash
uv sync
```

3. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

4. Configure your environment variables in `.env`:
   - `DATABASE_URL`: PostgreSQL connection string
   - Other configuration options as needed

## Database Setup

The system requires a PostgreSQL database with PostGIS extension. The database schema will be created automatically on first run.

### Database Migrations

Database schema changes are managed through SQL migration files in the `migrations/` directory. To apply migrations:

```bash
# Run all pending migrations
uv run python run_migration.py

# Run a specific migration
uv run python run_migration.py migrations/001_add_gps_columns.sql
```

**Available Migrations:**
- `001_add_gps_columns.sql` - Adds longitude and latitude columns for GPS coordinates

For detailed information about creating and managing migrations, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

### Using Docker Compose (Recommended)

The easiest way to run the application is using Docker Compose, which sets up both the PostGIS database and the sync application.

#### Development Environment

1. **Start the services**:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

2. **View logs**:
```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.dev.yml logs -f sync-app
docker-compose -f docker-compose.dev.yml logs -f postgis
```

3. **Run sync job manually**:
```bash
docker-compose -f docker-compose.dev.yml exec sync-app uv run python -m src.scheduler
```

4. **Access the database**:
```bash
docker-compose -f docker-compose.dev.yml exec postgis psql -U postgres -d sensor_data
```

5. **Stop the services**:
```bash
docker-compose -f docker-compose.dev.yml down
```

6. **Stop and remove volumes** (deletes all data):
```bash
docker-compose -f docker-compose.dev.yml down -v
```

#### Development Features

The development Docker Compose configuration includes:
- **Hot-reloading**: Source code is mounted as a volume for live updates
- **Debug logging**: `LOG_LEVEL` set to `DEBUG`
- **Port exposure**: PostgreSQL port 5432 exposed for local access
- **Persistent volumes**: Database data persists between restarts
- **Health checks**: Ensures database is ready before starting sync app

#### Environment Variables

Environment variables are pre-configured in `docker-compose.dev.yml` but can be overridden in the `.env` file.

### Manual Setup

1. Create a PostgreSQL database:
```sql
CREATE DATABASE sensor_data;
```

2. Enable PostGIS extension:
```sql
\c sensor_data
CREATE EXTENSION postgis;
```

3. Update the `DATABASE_URL` in your `.env` file.

4. Run database migrations:
```bash
uv run python run_migration.py
```

This will create the necessary tables and apply any schema updates.

## Usage

### Running Manually

To run a sync job manually:

```bash
uv run python -m src.scheduler
```

### Scheduled Jobs with Cron

The sync job can be scheduled using cron. Example to run daily at 2 AM:

```bash
# Edit crontab
crontab -e

# Add this line to run sync daily at 2 AM
0 2 * * * cd /path/to/sensor-data-sync && uv run python -m src.scheduler >> /var/log/sensor-sync.log 2>&1
```

For Docker deployments, you can use an external cron job or a container-based cron solution.

## Development

### Project Dependencies

- `requests`: HTTP client for API calls
- `psycopg2-binary`: PostgreSQL database adapter
- `python-dotenv`: Environment variable management

### Development Dependencies

- `pytest`: Testing framework
- `hypothesis`: Property-based testing

### Running Tests

Tests will be added in future updates:

```bash
uv run pytest
```

## Architecture

The system follows an ETL (Extract, Transform, Load) pattern:

1. **Extract**: Fetch box metadata from API and archive files
2. **Transform**: Parse CSV sensor data and JSON metadata, sanitize names, aggregate by timestamp
3. **Load**: Upsert measurements into PostGIS database, merging multiple phenomena per timestamp

### Data Model

The system uses a **multi-phenomenon measurement model**:

- **One row per measurement**: Each unique (boxid, timestamp) combination creates one database row
- **Multiple phenomena per row**: Temperature, humidity, PM values, and other sensor readings are stored as columns
- **Upsert behavior**: When multiple sensor readings arrive for the same timestamp, they are merged into a single row using PostgreSQL's `ON CONFLICT DO UPDATE`
- **GPS coordinates**: Longitude and latitude are stored with each measurement for mobile sensor boxes

**Example**: A sensor box recording temperature, humidity, and PM2.5 at the same timestamp will create one row with all three values populated, rather than three separate rows.

### Components

- **API Client**: Handles HTTP requests to OpenSenseMap API and archive service
- **Data Parser**: Parses CSV sensor data and JSON metadata files
- **Database Manager**: Manages database connections, schema, and data insertion
- **Sync Coordinator**: Orchestrates the synchronization workflow and tracks state
- **Scheduler**: Main entry point for sync job execution

## Configuration

All configuration is done through environment variables. See `.env.example` for available options.

### Key Configuration Options

- `DATABASE_URL`: PostgreSQL connection string
- `GROUPTAGS`: Sensor box grouptags to sync (comma-separated, default: "atrai")
- `DEFAULT_START_DATE`: Start date for boxes with no sync history (default: "2024-01-01")
- `MAX_RETRIES`: Maximum retry attempts for failed API requests (default: 3)

## Error Handling

The system includes comprehensive error handling:

- **Network failures**: Automatic retry with exponential backoff
- **Missing data**: Graceful handling of missing archive files
- **Parsing errors**: Logs errors and continues processing
- **Database errors**: Transaction rollback and retry logic

## License

[License information to be added]

## Contributing

[Contributing guidelines to be added]
