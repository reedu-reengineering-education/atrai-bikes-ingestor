# Production Deployment Guide

This guide explains how to deploy the Sensor Data Synchronization System in a production environment using Docker Compose.

## Prerequisites

- Docker Engine 20.10 or later
- Docker Compose V2 or later
- At least 4GB RAM available
- At least 20GB disk space for database storage

## Quick Start

### 1. Prepare Environment Configuration

Copy the production environment template:

```bash
cp .env.prod.example .env.prod
```

Edit `.env.prod` and set the required values:

```bash
# REQUIRED: Set a strong database password
POSTGRES_PASSWORD=your_strong_password_here
```

**Security Note**: Generate a strong password using:
```bash
openssl rand -base64 32
```

### 2. Start Production Services

Start the services in detached mode:

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### 3. Verify Deployment

Check service status:

```bash
docker-compose -f docker-compose.prod.yml ps
```

Check logs:

```bash
# View all logs
docker-compose -f docker-compose.prod.yml logs

# Follow logs in real-time
docker-compose -f docker-compose.prod.yml logs -f

# View specific service logs
docker-compose -f docker-compose.prod.yml logs sync-app
docker-compose -f docker-compose.prod.yml logs postgis
```

### 4. Verify Database Connection

Check that the sync app can connect to the database:

```bash
docker-compose -f docker-compose.prod.yml exec sync-app python -c "from src.database import DatabaseManager; import os; db = DatabaseManager(os.getenv('DATABASE_URL')); print('Database connection successful')"
```

## Production Configuration Details

### PostGIS Service

**Production Settings:**
- **Restart Policy**: `always` - automatically restarts on failure
- **Resource Limits**: 
  - CPU: 2.0 cores max, 0.5 cores reserved
  - Memory: 2GB max, 512MB reserved
- **Health Check**: Runs every 30 seconds with 60-second startup grace period
- **Security**: 
  - No new privileges allowed
  - Runs as PostgreSQL default user (non-root)
- **Logging**: JSON format, 10MB max size, 3 file rotation
- **Port Exposure**: Not exposed externally by default (commented out)

**Data Persistence:**
- Volume: `postgis_data_prod`
- Location: `/var/lib/postgresql/data` inside container
- Driver: local (can be configured for network storage)

### Sync App Service

**Production Settings:**
- **Restart Policy**: `always` - automatically restarts on failure
- **Resource Limits**:
  - CPU: 1.0 core max, 0.25 cores reserved
  - Memory: 1GB max, 256MB reserved
- **Health Check**: Runs every 60 seconds
- **Security**:
  - Runs as user 1000:1000 (non-root)
  - Read-only root filesystem
  - No new privileges allowed
  - Writable tmpfs for /tmp and /app/.cache
- **Logging**: JSON format, 10MB max size, 5 file rotation
- **Command**: `python main.py` (runs the scheduler)

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password (must be strong) | `$(openssl rand -base64 32)` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_DB` | `sensor_data` | Database name |
| `POSTGRES_USER` | `postgres` | Database username |
| `OPENSENSEMAP_API_URL` | `https://api.opensensemap.org` | OpenSenseMap API URL |
| `OPENSENSEMAP_ARCHIVE_URL` | `https://archive.opensensemap.org` | Archive URL |
| `GROUPTAGS` | `atrai` | Sensor box grouptags (comma-separated) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DEFAULT_START_DATE` | `2024-01-01` | Default sync start date |
| `MAX_RETRIES` | `3` | Max API retry attempts |
| `INITIAL_RETRY_DELAY` | `1.0` | Initial retry delay (seconds) |
| `MAX_RETRY_DELAY` | `60.0` | Max retry delay (seconds) |

## Management Commands

### Start Services

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Stop Services

```bash
docker-compose -f docker-compose.prod.yml down
```

### Restart Services

```bash
docker-compose -f docker-compose.prod.yml restart
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f sync-app
```

### Execute Commands in Container

```bash
# Access sync app shell
docker-compose -f docker-compose.prod.yml exec sync-app /bin/bash

# Access PostgreSQL shell
docker-compose -f docker-compose.prod.yml exec postgis psql -U postgres -d sensor_data
```

### Update Services

```bash
# Pull latest images
docker-compose -f docker-compose.prod.yml pull

# Rebuild and restart
docker-compose -f docker-compose.prod.yml up -d --build
```

## Backup and Recovery

### Database Backup

Create a backup of the PostgreSQL database:

```bash
# Create backup directory
mkdir -p backups

# Backup database
docker-compose -f docker-compose.prod.yml exec -T postgis pg_dump -U postgres sensor_data > backups/sensor_data_$(date +%Y%m%d_%H%M%S).sql
```

### Database Restore

Restore from a backup file:

```bash
# Restore database
docker-compose -f docker-compose.prod.yml exec -T postgis psql -U postgres sensor_data < backups/sensor_data_YYYYMMDD_HHMMSS.sql
```

### Volume Backup

Backup the entire data volume:

```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Backup volume
docker run --rm -v sensor-data-sync_postgis_data_prod:/data -v $(pwd)/backups:/backup alpine tar czf /backup/postgis_data_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# Restart services
docker-compose -f docker-compose.prod.yml up -d
```

## Monitoring

### Health Checks

Check service health:

```bash
docker-compose -f docker-compose.prod.yml ps
```

Healthy services show `(healthy)` status.

### Resource Usage

Monitor resource consumption:

```bash
docker stats sensor-data-postgis-prod sensor-data-sync-app-prod
```

### Log Monitoring

Monitor logs for errors:

```bash
# Watch for errors
docker-compose -f docker-compose.prod.yml logs -f | grep -i error

# Watch sync app logs
docker-compose -f docker-compose.prod.yml logs -f sync-app
```

## Security Best Practices

1. **Strong Passwords**: Use strong, randomly generated passwords
2. **Environment Files**: Never commit `.env.prod` to version control
3. **Port Exposure**: Keep database port unexposed (commented out in config)
4. **Regular Updates**: Keep Docker images updated
5. **Secrets Management**: Consider using Docker secrets or external secrets manager
6. **Network Isolation**: Use Docker networks to isolate services
7. **Read-Only Filesystem**: Sync app runs with read-only root filesystem
8. **Non-Root User**: Both services run as non-root users
9. **Resource Limits**: Prevent resource exhaustion with limits
10. **Log Rotation**: Automatic log rotation prevents disk filling

## Troubleshooting

### Services Won't Start

Check logs for errors:
```bash
docker-compose -f docker-compose.prod.yml logs
```

Common issues:
- Missing required environment variables (POSTGRES_PASSWORD)
- Port conflicts (if database port is exposed)
- Insufficient resources (check Docker resource limits)

### Database Connection Errors

Verify database is healthy:
```bash
docker-compose -f docker-compose.prod.yml ps postgis
```

Check database logs:
```bash
docker-compose -f docker-compose.prod.yml logs postgis
```

Test connection:
```bash
docker-compose -f docker-compose.prod.yml exec postgis pg_isready -U postgres
```

### Sync Job Not Running

Check sync app logs:
```bash
docker-compose -f docker-compose.prod.yml logs sync-app
```

Verify configuration:
- Check environment variables are set correctly
- Ensure the cron job is running (if using external cron)
- Check database connectivity

### High Resource Usage

Monitor resource consumption:
```bash
docker stats
```

Adjust resource limits in `docker-compose.prod.yml` if needed.

## Scaling Considerations

### Vertical Scaling

Adjust resource limits in `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'      # Increase CPU
      memory: 4G       # Increase memory
```

### Database Performance

For large datasets, consider:
- Increasing PostgreSQL shared_buffers
- Adding more indexes
- Using connection pooling
- Separating database to dedicated server

### Monitoring and Alerting

Consider integrating:
- Prometheus for metrics collection
- Grafana for visualization
- Alertmanager for notifications
- ELK stack for log aggregation

## Production Checklist

Before deploying to production:

- [ ] Set strong POSTGRES_PASSWORD
- [ ] Set up cron job for scheduled sync
- [ ] Review and adjust resource limits
- [ ] Set up database backup schedule
- [ ] Configure log monitoring/alerting
- [ ] Test backup and restore procedures
- [ ] Document incident response procedures
- [ ] Set up health check monitoring
- [ ] Review security settings
- [ ] Test failover scenarios
- [ ] Document rollback procedures
- [ ] Set up SSL/TLS if exposing services
- [ ] Configure firewall rules
- [ ] Set up monitoring dashboards

## Support

For issues or questions:
1. Check logs: `docker-compose -f docker-compose.prod.yml logs`
2. Review this documentation
3. Check cron job status
4. Verify environment configuration
5. Contact system administrator
