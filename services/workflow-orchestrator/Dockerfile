# =============================================================================
# WCT Workflow Orchestrator Service - Dockerfile
# Temporal-based durable workflow orchestration for Module 5 Case Audit
# =============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/workflow-orchestrator

WORKDIR /app

# Install system dependencies (curl for network checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared internal libraries
COPY libs/event-contracts/ /app/libs/event-contracts/
RUN pip install --no-cache-dir /app/libs/event-contracts/

# Copy Workflow Orchestrator service code and dependencies
COPY services/workflow-orchestrator/ /app/services/workflow-orchestrator/
RUN pip install --no-cache-dir /app/services/workflow-orchestrator/

# Copy mock data fixtures for local evidence resolution
COPY mock-data/ /app/mock-data/

WORKDIR /app/services/workflow-orchestrator

# Default container entrypoint: run the Temporal worker process
CMD ["python", "-m", "src.worker"]
