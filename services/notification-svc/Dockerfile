# =============================================================================
# WCT Notification Service - Dockerfile
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/notification-svc

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

# Copy Notification Service source code and configuration
COPY services/notification-svc/ /app/services/notification-svc/
RUN pip install --no-cache-dir /app/services/notification-svc/

WORKDIR /app/services/notification-svc

# Expose HTTP REST API port
EXPOSE 8003

# Health check against the /health endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Start FastAPI application using Uvicorn
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8003"]
