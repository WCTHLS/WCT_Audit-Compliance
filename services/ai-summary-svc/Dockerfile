# =============================================================================
# WCT AI Summary Service - Dockerfile
# Clinical narrative and risk explanation service for Module 5
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/ai-summary-svc

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install shared internal libraries
COPY libs/event-contracts/ /app/libs/event-contracts/
RUN pip install --no-cache-dir /app/libs/event-contracts/

COPY libs/evidence-lookup/ /app/libs/evidence-lookup/
RUN pip install --no-cache-dir /app/libs/evidence-lookup/

# Copy AI Summary Service code and install dependencies
COPY services/ai-summary-svc/ /app/services/ai-summary-svc/
RUN pip install --no-cache-dir /app/services/ai-summary-svc/

# Copy mock data fixtures
COPY mock-data/ /app/mock-data/

WORKDIR /app/services/ai-summary-svc

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
