FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# libspatialindex is needed by rtree/geopandas for spatial indexing.
# Other geospatial libs (GDAL, GEOS, PROJ) are bundled in the binary wheels
# (rasterio, shapely 2.x, pyproj) so no system GDAL install is required.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps — cached layer, only rebuilt when lockfile changes.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Application code
COPY src/        ./src/
COPY campaigns.yml migrations/ run_migration.py entrypoint.sh run_scheduler.py ./

# Put the venv on PATH so `uvicorn`, `python`, etc. resolve without `uv run`
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
