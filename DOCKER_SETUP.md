# Docker Setup Guide

This guide explains how to run the sensor data synchronization system using Docker Compose.

## Prerequisites

- Docker Engine 20.10 or higher
- Docker Compose V2 or higher

## Quick Start

1. **Clone the repository and navigate to the project directory**:
```bash
cd sensor-data-sync
```

2. **Create environment file**:
```bash
cp .env.example .env
```

3. **Start the development environment**:
```bash
docker-compose -f docker-compose.dev.yml up -d
```

5. **Check that services are running**:
```bash
docker-compose -f docker-compose.dev.yml ps
```

You should see two services running:
- `sensor-data-postgis-dev` (PostGIS database)
- `sensor-data-sync-app-dev` (Sync application)

## Development Workflow

### Running a Sync Job

Execute a sync job manually:
```bash
docker-compose -f docker-compose.dev.yml exec sync-app uv run python -m src.scheduler
```

### Viewing Logs

View logs from all services:
```bash
docker-compose -f docker-compose.dev.yml logs -f
```

View logs from a specific service:
```bash
docker-compose -f docker-compose.dev.yml logs -f sync-app
docker-compose -f docker-compose.dev.yml logs -f postgis
```

### Accessing the Database

Connect to the PostgreSQL database:
```bash
docker-compose -f docker-compose.dev.yml exec postgis psql -U postgres -d sensor_data
```

Or from your local machine (port 5432 is exposed):
```bash
psql -h localhost -U postgres -d sensor_data
# Password: password
```

### Running Tests

Execute tests inside the container:
```bash
docker-compose -f docker-compose.dev.yml exec sync-app uv run pytest
```

### Accessing the Sync App Shell

Get a shell inside the sync app container:
```bash
docker-compose -f docker-compose.dev.yml exec sync-app bash
```

### Restarting Services

Restart all services:
```bash
docker-compose -f docker-compose.dev.yml restart
```

Restart a specific service:
```bash
docker-compose -f docker-compose.dev.yml restart sync-app
```

### Stopping Services

Stop services (keeps data):
```bash
docker-compose -f docker-compose.dev.yml down
```

Stop services and remove volumes (deletes all data):
```bash
docker-compose -f docker-compose.dev.yml down -v
```

## Architecture

The Docker Compose setup includes:

### Services

1. **postgis**: PostgreSQL 16 with PostGIS 3.4 extension
   - Stores sensor measurements and sync state
   - Persistent volume for data storage
   - Health checks to ensure readiness
   - Port 5432 exposed for local access

2. **sync-app**: Python application with uv package manager
   - Runs sync jobs to fetch and store sensor data
   - Source code mounted as volume for hot-reloading
   - Waits for database health check before starting
   - Configured with environment variables

### Networks

- **sensor-sync-network**: Bridge network connecting services
  - Allows sync-app to communicate with postgis using service names
  - Isolated from other Docker networks

### Volumes

- **postgis_data_dev**: Persistent storage for PostgreSQL data
  - Data survives container restarts
  - Removed only with `docker-compose down -v`

- **uv_cache_dev**: Cache for uv package manager
  - Speeds up dependency installation
  - Shared across container rebuilds

## Configuration

### Environment Variables

The following environment variables are configured in `docker-compose.dev.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:password@postgis:5432/sensor_data` | PostgreSQL connection string |
| `OPENSENSEMAP_API_URL` | `https://api.opensensemap.org` | OpenSenseMap API base URL |
| `OPENSENSEMAP_ARCHIVE_URL` | `https://archive.opensensemap.org` | Archive service base URL |
| `GROUPTAGS` | `atrai` | Sensor box grouptags (comma-separated) |
| `LOG_LEVEL` | `DEBUG` | Logging level (DEBUG in dev) |
| `DEFAULT_START_DATE` | `2024-01-01` | Default sync start date |
| `MAX_RETRIES` | `3` | Max API request retries |
| `PYTHONUNBUFFERED` | `1` | Disable Python output buffering |

### Overriding Configuration

You can override any environment variable by adding it to your `.env` file:

```bash
# .env
LOG_LEVEL=INFO
GROUPTAGS=atrai,lauds_26
```

## Troubleshooting

### Database Connection Issues

If the sync app cannot connect to the database:

1. Check that the postgis service is healthy:
```bash
docker-compose -f docker-compose.dev.yml ps
```

2. Check postgis logs:
```bash
docker-compose -f docker-compose.dev.yml logs postgis
```

3. Verify the database is accepting connections:
```bash
docker-compose -f docker-compose.dev.yml exec postgis pg_isready -U postgres
```

### Port Already in Use

If port 5432 is already in use on your host:

1. Stop any local PostgreSQL instances
2. Or modify the port mapping in `docker-compose.dev.yml`:
```yaml
ports:
  - "5433:5432"  # Use port 5433 on host
```

### Container Build Issues

If the sync-app container fails to build:

1. Check Docker logs:
```bash
docker-compose -f docker-compose.dev.yml logs sync-app
```

2. Rebuild without cache:
```bash
docker-compose -f docker-compose.dev.yml build --no-cache sync-app
```

3. Verify Dockerfile syntax:
```bash
docker build -f Dockerfile --target development .
```

### Volume Permission Issues

If you encounter permission errors with volumes:

1. Check volume ownership:
```bash
docker-compose -f docker-compose.dev.yml exec sync-app ls -la /app
```

2. If needed, rebuild with proper user permissions (add to Dockerfile):
```dockerfile
RUN useradd -m -u 1000 appuser
USER appuser
```

## Production Deployment

For production deployment, use `docker-compose.prod.yml` (to be created in task 8.2):

```bash
docker-compose -f docker-compose.prod.yml up -d
```

Production configuration includes:
- Optimized resource limits
- Automatic restart policies
- Production logging levels
- No source code mounting
- Scheduled job execution

## Next Steps

- Set up a cron job for automated scheduling
- Set up monitoring and alerting
- Configure backup strategy for PostgreSQL data
- Review and adjust resource limits for production

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [PostGIS Docker Image](https://registry.hub.docker.com/r/postgis/postgis/)
- [uv Package Manager](https://github.com/astral-sh/uv)
