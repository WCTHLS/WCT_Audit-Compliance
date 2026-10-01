# =============================================================================
# WCT Exclusion Screening Service - Dockerfile
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/exclusion-screening-svc

WORKDIR /app

# Install system dependencies (curl for container health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared internal libraries
COPY libs/event-contracts/ /app/libs/event-contracts/
RUN pip install --no-cache-dir /app/libs/event-contracts/

COPY libs/auth-middleware/ /app/libs/auth-middleware/
RUN pip install --no-cache-dir /app/libs/auth-middleware/

COPY libs/evidence-lookup/ /app/libs/evidence-lookup/
RUN pip install --no-cache-dir /app/libs/evidence-lookup/

# Copy Exclusion Screening Service source code and configuration
COPY services/exclusion-screening-svc/ /app/services/exclusion-screening-svc/
RUN pip install --no-cache-dir /app/services/exclusion-screening-svc/

# Copy mock data for local POC evidence resolution
COPY mock-data/ /app/mock-data/

WORKDIR /app/services/exclusion-screening-svc

# Expose HTTP REST API port
EXPOSE 8002

# Health check against the /health endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Start FastAPI application using Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
