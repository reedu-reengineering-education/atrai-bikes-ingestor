# Multi-stage Dockerfile for sensor data sync application
# Supports both development and production builds

# Base stage with Python and uv
FROM python:3.12-slim as base

# Install system dependencies and uv
RUN apt-get update && apt-get install -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app

# Copy dependency files and README (needed for hatch build)
COPY pyproject.toml uv.lock README.md ./

# Development stage
FROM base as development
ENV PATH="/root/.local/bin:${PATH}"

RUN uv sync --all-extras

COPY src/ ./src/

CMD ["tail", "-f", "/dev/null"]

# Production stage
FROM base as production
ENV PATH="/root/.local/bin:${PATH}"

RUN uv sync --no-dev

COPY src/ ./src/

CMD ["uv", "run", "python", "-m", "src.scheduler"]
