"""
Pydantic schemas and Enums for the WCT Notification Service.
Defines contracts for alerts, dispatches, reminders, and delivery statuses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationType(str, Enum):
    """Supported types of notifications within the audit & compliance workflow."""
    CASE_ASSIGNMENT = "CASE_ASSIGNMENT"
    DOCUMENT_REQUEST_INITIAL = "DOCUMENT_REQUEST_INITIAL"
    DOCUMENT_REQUEST_REMINDER = "DOCUMENT_REQUEST_REMINDER"
    AUDITOR_ESCALATION = "AUDITOR_ESCALATION"
    SLA_BREACH_WARNING = "SLA_BREACH_WARNING"
    SLA_BREACH = "SLA_BREACH"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class NotificationChannel(str, Enum):
    """Delivery channels."""
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"
    WEBHOOK = "WEBHOOK"
    CONSOLE = "CONSOLE"


class NotificationPriority(str, Enum):
    """Priority levels for dispatch routing and SLA urgency."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NotificationStatus(str, Enum):
    """Delivery statuses."""
    DELIVERED = "DELIVERED"
    QUEUED = "QUEUED"
    FAILED = "FAILED"


class NotifyRequest(BaseModel):
    """Incoming notification dispatch request payload."""
    model_config = ConfigDict(extra="ignore")

    recipient: str = Field(
        ...,
        description="Target recipient identifier (email address, phone number, NPI, or auditor username)",
        examples=["auditor.smith@wct-health.com", "1093847562"],
    )
    notification_type: NotificationType = Field(
        ...,
        description="Classification of notification determining handling and urgency",
    )
    channel: NotificationChannel = Field(
        default=NotificationChannel.CONSOLE,
        description="Delivery mechanism (defaults to CONSOLE for local POC)",
    )
    priority: NotificationPriority = Field(
        default=NotificationPriority.NORMAL,
        description="Urgency of the alert",
    )
    subject: str = Field(
        ...,
        description="Short subject header or alert title",
        examples=["URGENT: Impending 72h SLA Breach on Case CASE-2026-001"],
    )
    message: str = Field(
        ...,
        description="Body text of the notification",
    )
    case_id: Optional[str] = Field(
        default=None,
        description="Associated case identifier for correlation",
        examples=["CASE-2026-001"],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional contextual metadata (e.g. reminder_number, hours_remaining, provider_npi)",
    )


class NotifyResponse(BaseModel):
    """Delivery confirmation response."""
    model_config = ConfigDict(extra="ignore")

    notification_id: str = Field(..., description="Unique dispatch identifier")
    status: NotificationStatus = Field(..., description="Delivery status")
    recipient: str = Field(..., description="Target recipient")
    channel: NotificationChannel = Field(..., description="Channel used")
    notification_type: NotificationType = Field(..., description="Notification classification")
    case_id: Optional[str] = Field(default=None, description="Correlated case ID")
    subject: str = Field(..., description="Alert subject")
    dispatched_at: str = Field(..., description="ISO 8601 UTC timestamp of dispatch")
    provider: str = Field(..., description="Underlying provider implementation used")
    details: str = Field(default="Notification delivered successfully.", description="Execution notes or response")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Echo of contextual metadata")


class HealthResponse(BaseModel):
    """Health status and telemetry."""
    status: str
    service: str
    active_providers: List[str]
    total_dispatched: int
    stats_by_type: Dict[str, int]
    stats_by_channel: Dict[str, int]
    timestamp: str
