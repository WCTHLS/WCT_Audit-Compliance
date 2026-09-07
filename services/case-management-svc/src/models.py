"""
SQLAlchemy ORM models for Case Management Service.
Defines the `cases` table representing the primary system of record for audit cases.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Boolean,
    Text,
    Date,
    DateTime,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from src.database import Base

# Portable JSON type: uses JSONB on PostgreSQL for high-performance indexing,
# and falls back to standard JSON on SQLite for fast isolated unit tests.
JSONType = JSON().with_variant(JSONB, "postgresql")


class Case(Base):
    """
    Case entity representing a healthcare audit case in WCT Module 5.
    Tracks case lifecycle, clinical evidence pointers, 72-hour SLA clock, and human decisions.
    """

    __tablename__ = "cases"

    # --- Core Identifiers ---
    case_id = Column(
        String(64),
        primary_key=True,
        index=True,
        doc="Unique case identifier (e.g. CASE-2026-001)",
    )
    claim_ref = Column(
        String(64),
        nullable=False,
        index=True,
        doc="Upstream claim reference ID (e.g. CLM-99214-8841)",
    )

    # --- Audit Lifecycle & Origin ---
    status = Column(
        String(32),
        nullable=False,
        default="NEW",
        index=True,
        doc="Current lifecycle state: NEW, ENRICHING, READY_FOR_REVIEW, DOCS_REQUESTED, DECISION_RECORDED, DISPUTED, CLOSED",
    )
    risk_score = Column(
        Integer,
        nullable=False,
        doc="Anomaly risk score from upstream ML models (100-1000)",
    )
    flagged_reason = Column(
        Text,
        nullable=False,
        doc="Detailed explanation of why the claim was flagged",
    )
    source_module = Column(
        String(32),
        nullable=False,
        default="fwa_detection",
        doc="Originating module (fwa_detection, payment_integrity)",
    )
    is_synthetic = Column(
        Boolean,
        nullable=False,
        default=True,
        doc="Flag indicating synthetic/mock data for safe teardown",
    )

    # --- Healthcare & Clinical Context ---
    facility_npi = Column(
        String(10),
        nullable=False,
        doc="10-digit NPI of the billing hospital / facility",
    )
    facility_name = Column(
        String(255),
        nullable=False,
        doc="Hospital or medical facility legal name",
    )
    doctor_npi = Column(
        String(10),
        nullable=False,
        doc="10-digit NPI of the rendering physician",
    )
    doctor_name = Column(
        String(255),
        nullable=False,
        doc="Rendering physician full name",
    )
    patient_id = Column(
        String(64),
        nullable=True,
        doc="De-identified patient ID (e.g. PAT-44910)",
    )
    service_date = Column(
        Date,
        nullable=True,
        doc="Date of medical service",
    )
    total_claim_amount = Column(
        Numeric(12, 2),
        nullable=False,
        doc="Total billed dollar amount under audit",
    )

    # --- Evidence Pointers (Architecture v0.3 / v0.4 Key Field) ---
    evidence_pointers = Column(
        JSONType,
        nullable=False,
        doc="JSON object with pointers to clinical notes, SHAP risk factors, peer comparison distribution, and claim flags",
    )

    # --- Auditor Assignment & SLA Management (PRD Mandate: 72h SLA) ---
    assigned_auditor = Column(
        String(128),
        nullable=True,
        index=True,
        doc="Username / email of the assigned human auditor",
    )
    sla_due_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        doc="Timestamp deadline for 72-hour human confirmation SLA",
    )
    sla_type = Column(
        String(32),
        nullable=False,
        default="INITIAL_REVIEW",
        doc="Governing SLA type: INITIAL_REVIEW, DOCS_RESPONSE, APPEAL_REVIEW",
    )
    sla_breached = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if the SLA window was breached before decision recording",
    )

    # --- Human Decision & Regulatory Compliance Audit Trail ---
    decision = Column(
        String(32),
        nullable=True,
        doc="Auditor decision: UPHOLD, REVERSE, REQUEST_INFO",
    )
    decision_rationale = Column(
        Text,
        nullable=True,
        doc="Human auditor written justification for the decision",
    )
    regulatory_basis = Column(
        String(255),
        nullable=True,
        doc="Regulatory citation (e.g. CMS NCCI Chapter 11, LCD 34567, 42 CFR 410.20)",
    )
    decided_by = Column(
        String(128),
        nullable=True,
        doc="User ID / email of the auditor who recorded the decision",
    )
    decided_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when the decision was officially recorded",
    )

    # --- Record Timestamps ---
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        doc="Timestamp when case was created in Module 5",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        doc="Timestamp of last case modification",
    )

    def __repr__(self) -> str:
        return (
            f"<Case(case_id='{self.case_id}', claim_ref='{self.claim_ref}', "
            f"status='{self.status}', risk_score={self.risk_score})>"
        )
