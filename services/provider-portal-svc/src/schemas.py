"""
Pydantic schemas for Provider Portal Service.
Defines contracts for document requests, read receipts, and provider responses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RequestStatusEnum(str, Enum):
    """Lifecycle states of a document request."""
    REQUESTED = "REQUESTED"      # Auditor created the request; awaiting provider viewing
    VIEWED = "VIEWED"            # Provider has opened/viewed the request (read receipt recorded)
    RESPONDED = "RESPONDED"      # Provider submitted documentation/response
    CANCELLED = "CANCELLED"      # Auditor withdrew or cancelled the request


class DocumentFileAttachment(BaseModel):
    """Metadata describing a file uploaded or attached by the provider."""
    model_config = ConfigDict(extra="ignore")

    filename: str = Field(..., description="Name of the uploaded file")
    file_type: str = Field(default="application/pdf", description="MIME type of document")
    file_size_bytes: int = Field(default=0, ge=0, description="Size in bytes")
    storage_uri: Optional[str] = Field(None, description="Object storage reference (e.g. s3:// or local key)")
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when file was uploaded",
    )


class DocumentRequestCreate(BaseModel):
    """Payload sent by auditor to request documents from a healthcare provider."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., min_length=1, description="Audit Case ID (e.g. CASE-2026-001)")
    provider_npi: str = Field(..., min_length=10, max_length=10, description="10-digit Rendering/Billing Provider NPI")
    requested_documents: List[str] = Field(
        ...,
        min_length=1,
        description="List of requested document items (e.g. ['Operative Report', 'Signed Progress Notes'])",
    )
    due_date: Optional[datetime] = Field(
        None,
        description="Target deadline for provider document submission",
    )
    provider_name: Optional[str] = Field(None, description="Provider or clinic legal name")
    provider_email: Optional[str] = Field(None, description="Contact email for notification dispatches")
    instructions: Optional[str] = Field(
        None,
        description="Special guidance or medical necessity audit instructions for the provider",
    )
    requested_by: str = Field(
        default="auditor@wct-health.com",
        description="Email or ID of requesting auditor",
    )


class DocumentResponseCreate(BaseModel):
    """Payload submitted by healthcare provider to respond to a document request."""
    model_config = ConfigDict(extra="ignore")

    response_notes: str = Field(
        ...,
        min_length=1,
        description="Provider clinical notes, justification, or submission narrative",
    )
    responded_by: Optional[str] = Field(
        default="provider-portal-user",
        description="Name or email of individual submitting records",
    )
    attachments: List[DocumentFileAttachment] = Field(
        default_factory=list,
        description="Attached documents or file metadata",
    )


class ReadReceiptRequest(BaseModel):
    """Optional metadata captured when a provider opens the request."""
    model_config = ConfigDict(extra="ignore")

    reader_identity: Optional[str] = Field(None, description="Identity of provider user viewing request")
    user_agent: Optional[str] = Field(None, description="Browser or client user agent")


class DocumentRequestResponse(BaseModel):
    """Complete document request representation returned by the API."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique document request identifier (e.g. DOCREQ-20261008-ABC123)")
    case_id: str
    provider_npi: str
    provider_name: Optional[str] = None
    provider_email: Optional[str] = None
    requested_documents: List[str]
    instructions: Optional[str] = None
    status: RequestStatusEnum
    requested_by: str
    created_at: datetime
    due_date: Optional[datetime] = None

    # Read Receipt Tracking
    read_at: Optional[datetime] = Field(None, description="First timestamp when request was opened")
    read_count: int = Field(default=0, description="Number of times request was viewed")
    last_read_at: Optional[datetime] = Field(None, description="Most recent view timestamp")

    # Provider Response
    response_notes: Optional[str] = None
    responded_by: Optional[str] = None
    responded_at: Optional[datetime] = None
    attachments: List[DocumentFileAttachment] = Field(default_factory=list)

    # Follow-Up Context
    reminders_sent: int = Field(default=0, description="Count of follow-up reminders dispatched")
    last_reminder_sent_at: Optional[datetime] = None


class DocumentRequestListResponse(BaseModel):
    """Paginated or filtered list of document requests with summary counts."""
    total: int
    requested_count: int
    viewed_count: int
    responded_count: int
    items: List[DocumentRequestResponse]
