# Haar Weather - Docker Image
# Multi-stage build for smaller image size

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libeccodes-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY haar/ haar/

# Install dependencies
RUN pip install --no-cache-dir -e .

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for eccodes (cfgrib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libeccodes0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY haar/ haar/
COPY pyproject.toml .
COPY config/ config/

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HAAR_DATA_DIR=/app/data
ENV HAAR_CONFIG_FILE=/app/config/haar.toml

# Default command shows help
ENTRYPOINT ["python", "-m", "haar.cli"]
CMD ["--help"]
