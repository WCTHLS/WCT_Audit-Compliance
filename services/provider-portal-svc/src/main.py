"""
FastAPI application for Provider Portal Service.
Provides endpoints for auditor document requests, read receipts, and provider responses.
"""

from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.repository import repository
from src.schemas import (
    DocumentRequestCreate,
    DocumentRequestListResponse,
    DocumentRequestResponse,
    DocumentResponseCreate,
    ReadReceiptRequest,
    RequestStatusEnum,
)

logger = logging.getLogger("provider_portal")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan lifecycle management."""
    logger.info(f"Starting {settings.SERVICE_NAME} on port {settings.SERVICE_PORT}...")
    yield
    logger.info(f"Shutting down {settings.SERVICE_NAME}...")


app = FastAPI(
    title="WCT Provider Portal Service",
    description=(
        "Handles auditor document requests to healthcare providers, tracks read receipts, "
        "and collects submitted medical records and responses for WCT Module 5."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware for auditor-workbench and provider portal frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"], summary="Health Check")
async def health_check() -> Dict[str, Any]:
    """Liveness probe reporting service status and total stored requests."""
    items = repository.list_all()
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "total_requests": len(items),
    }


@app.post(
    "/document-requests",
    response_model=DocumentRequestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Document Requests"],
    summary="Auditor requests medical records from a provider",
)
async def create_document_request(payload: DocumentRequestCreate) -> DocumentRequestResponse:
    """
    Called by an auditor to formally request clinical documentation
    from a healthcare provider for a specific case.
    """
    logger.info(
        f"Creating document request for case '{payload.case_id}', "
        f"provider NPI '{payload.provider_npi}', documents: {payload.requested_documents}"
    )
    record = repository.create(payload)
    return record


@app.get(
    "/document-requests",
    response_model=DocumentRequestListResponse,
    tags=["Document Requests"],
    summary="List all document requests with lifecycle summary counts",
)
async def list_document_requests() -> DocumentRequestListResponse:
    """Returns all document requests ordered by creation timestamp."""
    items = repository.list_all()
    return DocumentRequestListResponse(
        total=len(items),
        requested_count=sum(1 for i in items if i.status == RequestStatusEnum.REQUESTED),
        viewed_count=sum(1 for i in items if i.status == RequestStatusEnum.VIEWED),
        responded_count=sum(1 for i in items if i.status == RequestStatusEnum.RESPONDED),
        items=items,
    )


@app.get(
    "/document-requests/{id}",
    response_model=DocumentRequestResponse,
    tags=["Document Requests"],
    summary="Retrieve details of a document request",
)
async def get_document_request(
    id: str,
    mark_as_read: bool = Query(
        False,
        description="Set to true if viewed by the provider to automatically record a read receipt",
    ),
) -> DocumentRequestResponse:
    """
    Retrieves full details of a document request.
    If viewed by the provider, optionally records a read receipt.
    """
    if mark_as_read:
        updated = repository.record_read(id)
        if updated:
            return updated

    record = repository.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document request '{id}' not found.",
        )
    return record


@app.get(
    "/document-requests/case/{case_id}",
    response_model=List[DocumentRequestResponse],
    tags=["Document Requests"],
    summary="List all document requests for a specific audit case",
)
async def list_requests_for_case(case_id: str) -> List[DocumentRequestResponse]:
    """Returns all documentation requests associated with a case ID."""
    return repository.list_by_case(case_id)


@app.get(
    "/document-requests/provider/{provider_npi}",
    response_model=List[DocumentRequestResponse],
    tags=["Document Requests"],
    summary="List all document requests for a specific provider NPI",
)
async def list_requests_for_provider(provider_npi: str) -> List[DocumentRequestResponse]:
    """Returns all requests directed to a specific provider NPI."""
    return repository.list_by_provider(provider_npi)


@app.post(
    "/document-requests/{id}/read",
    response_model=DocumentRequestResponse,
    tags=["Read Receipts"],
    summary="Record a read receipt when provider opens the request",
)
async def record_read_receipt(
    id: str,
    payload: Optional[ReadReceiptRequest] = None,
) -> DocumentRequestResponse:
    """
    Records that the provider has opened or inspected the request.
    Transitions status to VIEWED and timestamps read_at.
    Feeds the automated follow-up reminder logic to distinguish
    unread requests from ignored/in-progress requests.
    """
    updated = repository.record_read(id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document request '{id}' not found.",
        )
    logger.info(f"Recorded read receipt for request '{id}' (read_count={updated.read_count}).")
    return updated


@app.post(
    "/document-requests/{id}/respond",
    response_model=DocumentRequestResponse,
    tags=["Provider Response"],
    summary="Provider submits requested records and response",
)
async def respond_to_document_request(
    id: str,
    payload: DocumentResponseCreate,
) -> DocumentRequestResponse:
    """
    Provider responds to the auditor's request with clinical notes,
    justifications, and attached document metadata.
    Transitions status to RESPONDED.
    """
    record = repository.get(id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document request '{id}' not found.",
        )

    if record.status == RequestStatusEnum.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot respond to cancelled document request '{id}'.",
        )

    updated = repository.submit_response(id, payload)
    logger.info(
        f"Provider response submitted for request '{id}' by '{payload.responded_by}'. "
        f"Attachments: {len(payload.attachments)}"
    )
    return updated


@app.post(
    "/document-requests/{id}/reminder",
    response_model=DocumentRequestResponse,
    tags=["Follow-Up"],
    summary="Record that a follow-up reminder was dispatched to the provider",
)
async def record_follow_up_reminder(id: str) -> DocumentRequestResponse:
    """
    Called when an automated follow-up reminder is dispatched for an unfulfilled request.
    Increments reminder count.
    """
    updated = repository.record_reminder_sent(id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document request '{id}' not found.",
        )
    logger.info(f"Recorded reminder dispatch #{updated.reminders_sent} for request '{id}'.")
    return updated


@app.post(
    "/document-requests/{id}/cancel",
    response_model=DocumentRequestResponse,
    tags=["Document Requests"],
    summary="Auditor cancels/withdraws a document request",
)
async def cancel_document_request(id: str) -> DocumentRequestResponse:
    """Auditor withdraws or cancels the document request."""
    updated = repository.cancel(id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document request '{id}' not found.",
        )
    logger.info(f"Document request '{id}' has been cancelled.")
    return updated
