"""
Pydantic schemas for Case Management Service.
Reuses domain enums and evidence contracts from `wct-event-contracts`
and defines request/response models for CRUD operations.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from event_contracts import (
    CaseStatusEnum,
    SlaTypeEnum,
    AuditDecisionEnum,
    EvidencePointers,
)


class CaseBase(BaseModel):
    """Base attributes shared across Case schemas."""
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    claim_ref: str = Field(..., min_length=1, description="Claim reference ID (e.g. CLM-99214-8841)")
    risk_score: int = Field(..., ge=100, le=1000, description="FWA ML risk score (100-1000)")
    flagged_reason: str = Field(..., min_length=1, description="Detailed reason for audit flag")
    source_module: str = Field(default="fwa_detection", description="Originating source module")
    is_synthetic: bool = Field(default=True, description="Indicates mock/test data for easy lifecycle teardown")

    facility_npi: str = Field(..., min_length=10, max_length=10, description="10-digit Hospital / Facility NPI")
    facility_name: str = Field(..., min_length=1, description="Hospital or medical facility legal name")
    doctor_npi: str = Field(..., min_length=10, max_length=10, description="10-digit Rendering Physician NPI")
    doctor_name: str = Field(..., min_length=1, description="Rendering doctor full name")
    patient_id: Optional[str] = Field(None, description="Anonymized patient identifier")
    service_date: Optional[date] = Field(None, description="Date of Service (DOS)")
    total_claim_amount: Decimal = Field(..., ge=0.0, description="Total billed claim dollar amount")
    evidence_pointers: EvidencePointers | Dict[str, Any] = Field(
        ..., description="Pointers to clinical, risk factors, and peer comparison evidence bundles"
    )


class CaseCreate(CaseBase):
    """Request schema for creating a new audit case."""
    case_id: str = Field(..., min_length=1, description="Unique case identifier (e.g. CASE-2026-001)")
    status: CaseStatusEnum = Field(default=CaseStatusEnum.NEW, description="Initial case lifecycle status")
    assigned_auditor: Optional[str] = Field(None, description="Assigned auditor user ID / email")
    sla_due_at: Optional[datetime] = Field(
        default=None,
        description="Deadline timestamp for SLA confirmation (defaults to now + 72 hours if omitted)",
    )
    sla_type: SlaTypeEnum = Field(
        default=SlaTypeEnum.INITIAL_REVIEW,
        description="Governing SLA timer type",
    )


class CaseUpdate(BaseModel):
    """
    Request schema for PATCH /cases/{id}.
    All fields are optional for partial updates (auditor assignment, state transition, decision recording).
    """
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    status: Optional[CaseStatusEnum] = Field(None, description="Updated case lifecycle status")
    assigned_auditor: Optional[str] = Field(None, description="Assigned human auditor email/ID")
    sla_breached: Optional[bool] = Field(None, description="Flag indicating SLA deadline breach")
    sla_due_at: Optional[datetime] = Field(None, description="Adjusted SLA deadline timestamp")
    sla_type: Optional[SlaTypeEnum] = Field(None, description="Active SLA timer type")

    # Auditor Decision Recording
    decision: Optional[AuditDecisionEnum] = Field(None, description="Auditor decision: UPHOLD, REVERSE, REQUEST_INFO")
    decision_rationale: Optional[str] = Field(None, min_length=1, description="Written justification for decision")
    regulatory_basis: Optional[str] = Field(None, description="Regulatory policy / NCCI citation")
    decided_by: Optional[str] = Field(None, description="User ID / email of the auditor who recorded the decision")
    decided_at: Optional[datetime] = Field(None, description="Timestamp when the decision was recorded")


class CaseRead(CaseBase):
    """Full case response schema returned on reads."""
    case_id: str = Field(..., description="Unique case identifier")
    status: CaseStatusEnum = Field(..., description="Current lifecycle state")
    assigned_auditor: Optional[str] = Field(None, description="Assigned auditor email/ID")
    sla_due_at: datetime = Field(..., description="Timestamp deadline for SLA")
    sla_type: SlaTypeEnum = Field(..., description="Active SLA timer type")
    sla_breached: bool = Field(default=False, description="Whether the SLA window was breached")

    decision: Optional[AuditDecisionEnum] = Field(None, description="Auditor decision")
    decision_rationale: Optional[str] = Field(None, description="Auditor decision rationale")
    regulatory_basis: Optional[str] = Field(None, description="Regulatory citation")
    decided_by: Optional[str] = Field(None, description="User ID of deciding auditor")
    decided_at: Optional[datetime] = Field(None, description="Decision timestamp")

    created_at: datetime = Field(..., description="Case creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CaseListResponse(BaseModel):
    """Paginated list of audit cases."""
    model_config = ConfigDict(from_attributes=True)

    items: List[CaseRead] = Field(..., description="List of cases matching query criteria")
    total: int = Field(..., ge=0, description="Total count of matching cases")
    skip: int = Field(default=0, ge=0, description="Number of skipped items")
    limit: int = Field(default=50, ge=1, description="Maximum items per page")
