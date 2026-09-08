"""
CRUD operations for Case Management Service.
Handles database queries, case creation with SLA calculation,
flexible query filtering, pagination, and partial updates.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from src.config import settings
from src.models import Case
from src.schemas import CaseCreate, CaseUpdate
from event_contracts import CaseStatusEnum, SlaTypeEnum, AuditDecisionEnum


def create_case(db: Session, case_in: CaseCreate) -> Case:
    """
    Creates and persists a new Case record in the PostgreSQL database.
    Calculates default 72-hour SLA deadline if sla_due_at is omitted.
    """
    now = datetime.now(timezone.utc)
    sla_due = case_in.sla_due_at or (now + timedelta(hours=settings.DEFAULT_SLA_HOURS))

    # Convert evidence_pointers to JSON serializable dict if it is a Pydantic model
    evidence_dict: Dict[str, Any]
    if isinstance(case_in.evidence_pointers, BaseModel):
        evidence_dict = case_in.evidence_pointers.model_dump(mode="json")
    elif isinstance(case_in.evidence_pointers, dict):
        evidence_dict = case_in.evidence_pointers
    else:
        evidence_dict = dict(case_in.evidence_pointers)

    db_case = Case(
        case_id=case_in.case_id,
        claim_ref=case_in.claim_ref,
        status=case_in.status.value if isinstance(case_in.status, CaseStatusEnum) else case_in.status,
        risk_score=case_in.risk_score,
        flagged_reason=case_in.flagged_reason,
        source_module=case_in.source_module,
        is_synthetic=case_in.is_synthetic,
        facility_npi=case_in.facility_npi,
        facility_name=case_in.facility_name,
        doctor_npi=case_in.doctor_npi,
        doctor_name=case_in.doctor_name,
        patient_id=case_in.patient_id,
        service_date=case_in.service_date,
        total_claim_amount=case_in.total_claim_amount,
        evidence_pointers=evidence_dict,
        assigned_auditor=case_in.assigned_auditor,
        sla_due_at=sla_due,
        sla_type=case_in.sla_type.value if isinstance(case_in.sla_type, SlaTypeEnum) else case_in.sla_type,
        sla_breached=False,
    )

    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    return db_case


def get_case_by_id(db: Session, case_id: str) -> Optional[Case]:
    """Retrieves a single case record by case_id primary key."""
    stmt = select(Case).where(Case.case_id == case_id)
    return db.execute(stmt).scalar_one_or_none()


def list_cases(
    db: Session,
    status: Optional[str] = None,
    assigned_auditor: Optional[str] = None,
    source_module: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Case], int]:
    """
    Queries case records with optional filtering and pagination.
    Returns (items, total_count).
    """
    query = select(Case)
    count_query = select(func.count()).select_from(Case)

    if status:
        query = query.where(Case.status == status)
        count_query = count_query.where(Case.status == status)

    if assigned_auditor:
        query = query.where(Case.assigned_auditor == assigned_auditor)
        count_query = count_query.where(Case.assigned_auditor == assigned_auditor)

    if source_module:
        query = query.where(Case.source_module == source_module)
        count_query = count_query.where(Case.source_module == source_module)

    if sla_breached is not None:
        query = query.where(Case.sla_breached == sla_breached)
        count_query = count_query.where(Case.sla_breached == sla_breached)

    total = db.execute(count_query).scalar_one()

    # Sort newest cases first
    query = query.order_by(desc(Case.created_at)).offset(skip).limit(limit)
    items = list(db.execute(query).scalars().all())

    return items, total


def update_case(db: Session, db_case: Case, case_in: CaseUpdate) -> Case:
    """
    Applies partial updates to an existing Case record (PATCH semantics).
    Supports auditor assignment, status transitions, and decision recording.
    """
    update_data = case_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        if value is None and field not in ("assigned_auditor", "decision", "decision_rationale", "regulatory_basis"):
            continue

        # Handle Enums
        if isinstance(value, (CaseStatusEnum, SlaTypeEnum, AuditDecisionEnum)):
            setattr(db_case, field, value.value)
        else:
            setattr(db_case, field, value)

    # Automatic decision handling
    if case_in.decision is not None:
        # Auto-set decided_at if not explicitly provided
        if not case_in.decided_at and not db_case.decided_at:
            db_case.decided_at = datetime.now(timezone.utc)

        # Auto-transition status to DECISION_RECORDED if status was not explicitly updated
        if "status" not in update_data:
            db_case.status = CaseStatusEnum.DECISION_RECORDED.value

    db.commit()
    db.refresh(db_case)
    return db_case
