# VIDEOCU v1 - Production Dockerfile
# Multi-stage build for optimized image size

# Stage 1: Base image with system dependencies
FROM python:3.11-slim-bullseye as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
# - FFmpeg: Video processing (MoviePy requirement)
# - PostgreSQL client: Database connectivity
# - Build essentials: Required for some Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libpq-dev \
        gcc \
        g++ \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 videocu && \
    mkdir -p /app /app/output && \
    chown -R videocu:videocu /app

# Stage 2: Dependencies installation
FROM base as dependencies

WORKDIR /app

# Copy requirements and install Python dependencies
COPY --chown=videocu:videocu requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Application
FROM dependencies as application

WORKDIR /app

# Copy application code
COPY --chown=videocu:videocu . .

# Create necessary directories
RUN mkdir -p \
    output \
    output/videos \
    output/temp \
    output/logs \
    modules/prompts \
    && chown -R videocu:videocu /app

# Switch to non-root user
USER videocu

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (overridden in docker-compose.yml)
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
