"""
Main entry point for WCT Notification Service.
Provides FastAPI endpoints for dispatching alerts, provider follow-ups,
and auditor escalations across the WCT Module 5 platform.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.providers.registry import registry
from src.repository import repository
from src.schemas import (
    HealthResponse,
    NotificationType,
    NotifyRequest,
    NotifyResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    print(f"[{settings.SERVICE_NAME}] Starting on port {settings.SERVICE_PORT}...", flush=True)
    yield
    print(f"[{settings.SERVICE_NAME}] Shutting down...", flush=True)


app = FastAPI(
    title="WCT Notification Service",
    description=(
        "Microservice for WCT Module 5 (Audit & Compliance). "
        "Dispatches SLA breach alerts, automated provider follow-up reminders (FR-AUD-03), "
        "and auditor escalations with a pluggable provider interface."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service Health & Telemetry",
)
async def health_check() -> HealthResponse:
    """
    Returns service liveness status, active notification providers,
    and real-time dispatch telemetry.
    """
    stats = repository.get_stats()
    return HealthResponse(
        status="healthy",
        service=settings.SERVICE_NAME,
        active_providers=registry.list_active(),
        total_dispatched=stats["total_dispatched"],
        stats_by_type=stats["stats_by_type"],
        stats_by_channel=stats["stats_by_channel"],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post(
    "/notify",
    response_model=NotifyResponse,
    status_code=status.HTTP_200_OK,
    tags=["Notifications"],
    summary="Dispatch a Notification",
)
async def dispatch_notification(payload: NotifyRequest) -> NotifyResponse:
    """
    Dispatches an alert or reminder using the active provider pipeline.
    
    Supported use cases:
    - SLA_BREACH_WARNING: Impending 72h SLA breach alert.
    - SLA_BREACH: Formal breach alert.
    - DOCUMENT_REQUEST_INITIAL: Initial records request to provider.
    - DOCUMENT_REQUEST_REMINDER: Automated follow-up reminder (FR-AUD-03).
    - AUDITOR_ESCALATION: Supervisory escalation for stalled reviews.
    - CASE_ASSIGNMENT: Assignment notification to auditor.
    - SYSTEM_ALERT: Platform infrastructure alert.
    """
    try:
        # Resolve active provider for this channel/dispatch
        provider = registry.get_default_provider(channel=payload.channel)
        
        # Dispatch notification
        response = await provider.send(payload)
        
        # Persist to in-memory dispatch history
        repository.add(response)
        
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Notification dispatch failed: {str(exc)}",
        )


@app.get(
    "/notifications",
    response_model=List[NotifyResponse],
    tags=["Notifications"],
    summary="List Dispatched Notifications",
)
async def list_notifications(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    recipient: Optional[str] = Query(None, description="Filter by recipient"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=200, description="Max entries to return"),
) -> List[NotifyResponse]:
    """
    Queries recent notification dispatch history with optional filters.
    """
    return repository.list_all(
        case_id=case_id,
        recipient=recipient,
        notification_type=notification_type,
        limit=limit,
    )


@app.get(
    "/notifications/{notification_id}",
    response_model=NotifyResponse,
    tags=["Notifications"],
    summary="Get Notification Details",
)
async def get_notification(notification_id: str) -> NotifyResponse:
    """
    Retrieves full details and receipt for a single notification ID.
    """
    item = repository.get_by_id(notification_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found.",
        )
    return item


@app.delete(
    "/notifications",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Testing & Maintenance"],
    summary="Clear Notification History",
)
async def clear_notifications() -> None:
    """Clears in-memory notification buffer (used for test setup/teardown)."""
    repository.clear()
