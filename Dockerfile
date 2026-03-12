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

# Install tini (init) and supercronic for cron scheduling
RUN apt-get update && apt-get install -y tini \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH=$(uname -m) \
    && case "$ARCH" in \
         aarch64) ARCH="arm64" ;; \
         x86_64) ARCH="amd64" ;; \
       esac \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-${ARCH}" \
         -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

RUN uv sync --no-dev

COPY src/ ./src/
COPY entrypoint.sh ./
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/entrypoint.sh"]
