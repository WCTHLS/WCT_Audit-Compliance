"""
Event contracts and schemas for WCT Module 5 (Audit & Compliance Workflow).

Contains:
- CaseCreatedEvent: Data ingress contract from FWA Detection.
- EvidencePointers & PeerComparisonData: Structured pointers to mock/upstream evidence bundles.
- CaseStatusChangedEvent: Internal lifecycle state transition contract with SLA tracking.
- Enums: CaseStatusEnum, SlaTypeEnum, AuditDecisionEnum.
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class CaseStatusEnum(str, Enum):
    """Lifecycle states of an audit case."""
    NEW = "NEW"
    ENRICHING = "ENRICHING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    DOCS_REQUESTED = "DOCS_REQUESTED"
    DECISION_RECORDED = "DECISION_RECORDED"
    DISPUTED = "DISPUTED"
    UNDER_APPEAL_REVIEW = "UNDER_APPEAL_REVIEW"
    APPEAL_SENT = "APPEAL_SENT"
    CLOSED = "CLOSED"


class SlaTypeEnum(str, Enum):
    """Type of SLA timer currently governing the case."""
    INITIAL_REVIEW = "INITIAL_REVIEW"   # Default 72h SLA timer for initial audit
    DOCS_RESPONSE = "DOCS_RESPONSE"     # Provider documentation request window
    APPEAL_REVIEW = "APPEAL_REVIEW"     # Re-review SLA after provider dispute


class AuditDecisionEnum(str, Enum):
    """Auditor decision actions."""
    UPHOLD = "UPHOLD"                   # Agree with FWA flag / uphold denial
    REVERSE = "REVERSE"                 # Overturn flag / approve claim payment
    REQUEST_INFO = "REQUEST_INFO"       # Request additional provider records


class PeerComparisonData(BaseModel):
    """
    Structured metrics and fixture pointer for provider peer comparison.
    Used by peer_comparison.py to compute percentile rank and median ratios deterministically.
    """
    model_config = ConfigDict(extra="ignore")

    specialty: str = Field(..., description="Provider medical specialty (e.g. Interventional Cardiology)")
    region: str = Field(..., description="Geographic region / peer market (e.g. US-Northeast, NY-Metro)")
    cohort_size: int = Field(..., ge=1, description="Number of peers in the specialty/region cohort")
    provider_metric_value: float = Field(..., ge=0.0, description="Provider's metric value (e.g. Mod 25 billing rate)")
    peer_median: float = Field(..., ge=0.0, description="Median metric value across the peer cohort")
    peer_percentile: Optional[float] = Field(None, ge=0.0, le=100.0, description="Computed percentile rank (0-100)")
    fixture_ref: Optional[str] = Field(None, description="Path or key to detailed peer distribution fixture")


class EvidencePointers(BaseModel):
    """
    Pointers to the upstream/mock evidence bundles referenced by the case.
    Enables microservices to retrieve clinical records, risk models, and peer stats.
    """
    model_config = ConfigDict(extra="ignore")

    clinical_evidence: str = Field(..., description="Path/URI to extracted clinical notes and claim lines fixture")
    risk_factors: str = Field(..., description="Path/URI to SHAP risk factors and model explainability fixture")
    peer_comparison: PeerComparisonData = Field(..., description="Peer benchmarking metrics and data reference")
    claim_flags: Optional[str] = Field(None, description="Path/URI to clinical edit rule flags fixture")


class CaseCreatedEvent(BaseModel):
    """
    Event contract for 'case.created' topic.
    Published by FWA Detection to initiate an audit case in Module 5.
    """
    model_config = ConfigDict(extra="ignore")

    # Event Envelope & Metadata
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event UUID")
    event_type: str = Field(default="case.created", description="Event topic name")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of trigger")
    source_module: str = Field(default="fwa_detection", description="Originating module provenance")
    is_synthetic: bool = Field(default=True, description="Flag indicating mock/test data for easy lifecycle teardown")

    # Core Identifiers
    case_id: str = Field(..., min_length=1, description="Case tracking ID (e.g. CASE-2026-001)")
    claim_ref: str = Field(..., min_length=1, description="Claim reference ID (e.g. CLM-99214-8841)")

    # Facility / Hospital (Billing Entity)
    facility_npi: str = Field(..., min_length=10, max_length=10, description="10-digit Hospital / Facility NPI")
    facility_name: str = Field(..., min_length=1, description="Hospital or medical facility legal name")

    # Doctor / Physician (Rendering Clinician)
    doctor_npi: str = Field(..., min_length=10, max_length=10, description="10-digit Rendering Physician NPI")
    doctor_name: str = Field(..., min_length=1, description="Rendering doctor full name")

    # Patient Context
    patient_id: Optional[str] = Field(None, description="Anonymized patient identifier (e.g. PAT-44910)")

    # Claim & Triage Data
    service_date: Optional[date] = Field(None, description="Date of Service (DOS) when medical care was provided")
    total_claim_amount: float = Field(..., ge=0.0, description="Total billed claim dollar amount")
    risk_score: int = Field(..., ge=100, le=1000, description="FWA ML risk score on a 100-1000 scale (>=500 is risky)")
    flagged_reason: str = Field(..., min_length=1, description="Detailed reason why the claim was flagged for audit")

    # Evidence Reference Bundle
    evidence_pointers: EvidencePointers = Field(..., description="Pointers to clinical, risk, and peer evidence bundles")


class DecisionSummary(BaseModel):
    """Summary of auditor decision and legal/regulatory rationale."""
    model_config = ConfigDict(extra="ignore")

    decision: AuditDecisionEnum = Field(..., description="Action taken: UPHOLD, REVERSE, or REQUEST_INFO")
    rationale: str = Field(..., min_length=1, description="Auditor's written explanation")
    regulatory_basis: Optional[str] = Field(None, description="Regulatory policy citation (e.g. CMS NCCI Policy Manual)")


class CaseStatusChangedEvent(BaseModel):
    """
    Event contract for 'case.status.changed' topic.
    Emitted internally on every case state transition for queue indexing, notifications, and audit logging.
    """
    model_config = ConfigDict(extra="ignore")

    # Event Envelope
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event UUID")
    event_type: str = Field(default="case.status.changed", description="Event topic name")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of transition")

    # Case & Transition Details
    case_id: str = Field(..., min_length=1, description="Case tracking ID")
    claim_ref: str = Field(..., min_length=1, description="Claim reference ID")
    previous_status: Optional[CaseStatusEnum] = Field(None, description="Status prior to transition (null for new cases)")
    new_status: CaseStatusEnum = Field(..., description="New case status")

    # Actor & Assignment
    changed_by: str = Field(..., min_length=1, description="User ID or service that initiated change")
    changed_by_role: str = Field(..., min_length=1, description="Role of actor (e.g. system, Auditor, Provider)")
    assigned_auditor_id: Optional[str] = Field(None, description="Assigned auditor user ID")
    reason: Optional[str] = Field(None, description="Description/reason for state change")

    # SLA Tracking & Deadlines
    sla_type: SlaTypeEnum = Field(default=SlaTypeEnum.INITIAL_REVIEW, description="Active SLA clock type")
    sla_due_at: Optional[datetime] = Field(None, description="Timestamp when current SLA expires")
    sla_breached: bool = Field(default=False, description="Flag indicating if SLA deadline has passed")

    # Decision Context
    decision_summary: Optional[DecisionSummary] = Field(None, description="Populated when new_status is DECISION_RECORDED")
