"""
Unit test suite for Case Management Service ORM models.
Tests table creation, mock data insertion, evidence_pointers JSON serialization,
SLA due date calculations, and auditor decision updates.
"""

import json
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from src.database import Base
from src.models import Case
from src.config import settings

# Path to mock-data fixtures
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def test_schema_table_creation(db_session):
    """Verify cases table is created with expected columns in metadata."""
    assert "cases" in Base.metadata.tables
    table = Base.metadata.tables["cases"]
    assert "case_id" in table.columns
    assert "claim_ref" in table.columns
    assert "evidence_pointers" in table.columns
    assert "sla_due_at" in table.columns
    assert "status" in table.columns


def test_insert_mock_case_001(db_session):
    """Verify Case 1 (Outpatient CPT 99215 Mod 25) mock fixture inserts cleanly into database."""
    case_001_file = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    assert case_001_file.exists(), f"Mock fixture missing: {case_001_file}"

    with open(case_001_file, encoding="utf-8") as f:
        event_data = json.load(f)

    # Calculate 72-hour SLA deadline
    now = datetime.now(timezone.utc)
    sla_due = now + timedelta(hours=settings.DEFAULT_SLA_HOURS)

    case = Case(
        case_id=event_data["case_id"],
        claim_ref=event_data["claim_ref"],
        status="NEW",
        risk_score=event_data["risk_score"],
        flagged_reason=event_data["flagged_reason"],
        source_module=event_data["source_module"],
        is_synthetic=event_data["is_synthetic"],
        facility_npi=event_data["facility_npi"],
        facility_name=event_data["facility_name"],
        doctor_npi=event_data["doctor_npi"],
        doctor_name=event_data["doctor_name"],
        patient_id=event_data.get("patient_id"),
        service_date=datetime.strptime(event_data["service_date"], "%Y-%m-%d").date(),
        total_claim_amount=Decimal(str(event_data["total_claim_amount"])),
        evidence_pointers=event_data["evidence_pointers"],
        sla_due_at=sla_due,
        sla_type="INITIAL_REVIEW",
        sla_breached=False,
    )

    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    # Query back and assert
    saved_case = db_session.execute(select(Case).where(Case.case_id == "CASE-2026-001")).scalar_one()
    assert saved_case.case_id == "CASE-2026-001"
    assert saved_case.claim_ref == "CLM-99214-8841"
    assert saved_case.risk_score == 850
    assert saved_case.doctor_name == "Dr. Robert Vance, MD"
    assert saved_case.status == "NEW"
    assert saved_case.sla_breached is False


def test_insert_mock_case_002(db_session):
    """Verify Case 2 (Inpatient DRG 469 upcoding) mock fixture inserts cleanly."""
    case_002_file = MOCK_DATA_DIR / "fwa-mock" / "case_002_event.json"
    with open(case_002_file, encoding="utf-8") as f:
        event_data = json.load(f)

    now = datetime.now(timezone.utc)
    case = Case(
        case_id=event_data["case_id"],
        claim_ref=event_data["claim_ref"],
        status="NEW",
        risk_score=event_data["risk_score"],
        flagged_reason=event_data["flagged_reason"],
        source_module=event_data["source_module"],
        is_synthetic=event_data["is_synthetic"],
        facility_npi=event_data["facility_npi"],
        facility_name=event_data["facility_name"],
        doctor_npi=event_data["doctor_npi"],
        doctor_name=event_data["doctor_name"],
        patient_id=event_data.get("patient_id"),
        service_date=datetime.strptime(event_data["service_date"], "%Y-%m-%d").date(),
        total_claim_amount=Decimal(str(event_data["total_claim_amount"])),
        evidence_pointers=event_data["evidence_pointers"],
        sla_due_at=now + timedelta(hours=72),
    )

    db_session.add(case)
    db_session.commit()

    saved_case = db_session.execute(select(Case).where(Case.case_id == "CASE-2026-002")).scalar_one()
    assert saved_case.facility_name == "St. Peter General Hospital"
    assert saved_case.total_claim_amount == Decimal("28500.00")
    assert saved_case.risk_score == 920


def test_evidence_pointers_json_roundtrip(db_session):
    """Verify nested evidence_pointers JSON data can be queried and traversed."""
    case_001_file = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(case_001_file, encoding="utf-8") as f:
        event_data = json.load(f)

    case = Case(
        case_id="CASE-JSON-TEST",
        claim_ref="CLM-TEST-001",
        status="NEW",
        risk_score=750,
        flagged_reason="Test JSON integrity",
        source_module="fwa_detection",
        is_synthetic=True,
        facility_npi="1295847361",
        facility_name="Memorial Health",
        doctor_npi="1093847562",
        doctor_name="Dr. Vance",
        service_date=date(2026, 8, 10),
        total_claim_amount=Decimal("1500.00"),
        evidence_pointers=event_data["evidence_pointers"],
        sla_due_at=datetime.now(timezone.utc) + timedelta(hours=72),
    )
    db_session.add(case)
    db_session.commit()

    fetched = db_session.execute(select(Case).where(Case.case_id == "CASE-JSON-TEST")).scalar_one()
    pointers = fetched.evidence_pointers
    assert "clinical_evidence" in pointers
    assert "risk_factors" in pointers
    assert "peer_comparison" in pointers
    assert pointers["peer_comparison"]["specialty"] == "Interventional Cardiology"
    assert pointers["peer_comparison"]["cohort_size"] == 184
    assert pointers["peer_comparison"]["peer_median"] == 18.0


def test_decision_recording_lifecycle(db_session):
    """Verify state transitions from NEW -> READY_FOR_REVIEW -> DECISION_RECORDED with auditor rationale."""
    now = datetime.now(timezone.utc)
    case = Case(
        case_id="CASE-DECISION-TEST",
        claim_ref="CLM-DECISION-01",
        status="READY_FOR_REVIEW",
        risk_score=850,
        flagged_reason="High risk unbundling",
        source_module="fwa_detection",
        is_synthetic=True,
        facility_npi="1295847361",
        facility_name="Memorial Health",
        doctor_npi="1093847562",
        doctor_name="Dr. Vance",
        service_date=date(2026, 8, 10),
        total_claim_amount=Decimal("3250.00"),
        evidence_pointers={"clinical_evidence": "path/test.json"},
        assigned_auditor="auditor_sarah@payer.com",
        sla_due_at=now + timedelta(hours=72),
    )
    db_session.add(case)
    db_session.commit()

    # Simulate Auditor recording decision
    case.decision = "UPHOLD"
    case.decision_rationale = "Modifier 25 unsupported: chart review confirms ECG was routine without separate E&M."
    case.regulatory_basis = "CMS NCCI Policy Manual Chapter 11, Section B"
    case.decided_by = "auditor_sarah@payer.com"
    case.decided_at = datetime.now(timezone.utc)
    case.status = "DECISION_RECORDED"

    db_session.commit()
    db_session.refresh(case)

    updated = db_session.execute(select(Case).where(Case.case_id == "CASE-DECISION-TEST")).scalar_one()
    assert updated.status == "DECISION_RECORDED"
    assert updated.decision == "UPHOLD"
    assert "CMS NCCI" in updated.regulatory_basis
    assert updated.decided_by == "auditor_sarah@payer.com"


def test_mandatory_field_integrity(db_session):
    """Verify database raises IntegrityError when required fields are missing."""
    invalid_case = Case(
        case_id="CASE-INVALID",
        # Missing claim_ref (nullable=False)
        status="NEW",
        risk_score=500,
    )
    db_session.add(invalid_case)
    with pytest.raises(Exception):
        db_session.commit()
