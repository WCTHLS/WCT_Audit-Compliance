"""
Unit and integration test suite for Case Management Service Kafka Consumer.
Tests event contract validation, idempotency handling, 72-hour SLA clock calculation,
and fixture ingestion using in-memory SQLite.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models import Case
from src.consumer import process_case_created_event, ingest_fixture_file, ConsumerError
from event_contracts import CaseCreatedEvent, CaseStatusEnum, SlaTypeEnum

# Path to mock-data fixtures
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def test_process_case_001_event_fixture(db_session):
    """Verify Case 1 mock event is successfully ingested with 72h SLA and evidence pointers."""
    fixture_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(fixture_path, encoding="utf-8") as f:
        payload = json.load(f)

    case = process_case_created_event(db_session, payload)

    assert case.case_id == "CASE-2026-001"
    assert case.claim_ref == "CLM-99214-8841"
    assert case.status == "NEW"
    assert case.risk_score == 850
    assert case.doctor_name == "Dr. Robert Vance, MD"
    assert case.facility_npi == "1295847361"
    assert case.sla_breached is False
    assert case.sla_type == "INITIAL_REVIEW"

    # Verify 72-hour SLA due date is accurately calculated
    expected_sla = datetime.fromisoformat(payload["timestamp"]) + timedelta(hours=72)
    case_sla = case.sla_due_at if case.sla_due_at.tzinfo else case.sla_due_at.replace(tzinfo=timezone.utc)
    assert abs((case_sla - expected_sla).total_seconds()) < 5

    # Verify evidence pointers are preserved
    assert "clinical_evidence" in case.evidence_pointers
    assert "risk_factors" in case.evidence_pointers
    assert "peer_comparison" in case.evidence_pointers


def test_process_case_002_event_fixture(db_session):
    """Verify Case 2 mock event (Inpatient DRG anomaly) is successfully ingested."""
    fixture_path = MOCK_DATA_DIR / "fwa-mock" / "case_002_event.json"
    with open(fixture_path, encoding="utf-8") as f:
        payload = json.load(f)

    case = process_case_created_event(db_session, payload)

    assert case.case_id == "CASE-2026-002"
    assert case.claim_ref == "CLM-DRG-469-1029"
    assert case.risk_score == 920
    assert case.facility_name == "St. Peter General Hospital"
    assert float(case.total_claim_amount) == 28500.00


def test_consumer_idempotency_on_duplicate_events(db_session):
    """
    Verify that consuming duplicate Kafka events (e.g. from retries/rebalances)
    does not create duplicate rows or raise errors.
    """
    fixture_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(fixture_path, encoding="utf-8") as f:
        payload = json.load(f)

    # First delivery
    case_first = process_case_created_event(db_session, payload)
    assert case_first.case_id == "CASE-2026-001"

    # Second delivery (duplicate message)
    case_second = process_case_created_event(db_session, payload)
    assert case_second.case_id == "CASE-2026-001"

    # Verify exactly 1 row exists in the cases table
    count = db_session.execute(select(func.count()).select_from(Case)).scalar_one()
    assert count == 1


def test_consumer_rejects_malformed_json(db_session):
    """Verify consumer raises ConsumerError on malformed JSON payload."""
    with pytest.raises(ConsumerError, match="Malformed JSON"):
        process_case_created_event(db_session, "{invalid json content:")


def test_consumer_rejects_schema_violation(db_session):
    """Verify consumer raises ConsumerError when event violates contract (e.g. invalid risk score)."""
    invalid_event = {
        "case_id": "CASE-INVALID",
        "claim_ref": "CLM-INVALID",
        "risk_score": 50,  # Invalid: must be >= 100
        "flagged_reason": "Test",
        "facility_npi": "1234567890",
        "facility_name": "Hospital",
        "doctor_npi": "1234567890",
        "doctor_name": "Doctor",
        "total_claim_amount": 100.0,
        "evidence_pointers": {
            "clinical_evidence": "fwa-mock/test.json",
            "risk_factors": "fwa-mock/test.json",
            "peer_comparison": {
                "specialty": "Cardiology",
                "region": "US-NE",
                "cohort_size": 50,
                "provider_metric_value": 0.5,
                "peer_median": 0.2,
            },
        },
    }

    with pytest.raises(ConsumerError, match="Schema validation error"):
        process_case_created_event(db_session, invalid_event)

    # Verify no rows were written
    count = db_session.execute(select(func.count()).select_from(Case)).scalar_one()
    assert count == 0


def test_ingest_fixture_file_helper(db_session):
    """Verify ingest_fixture_file successfully loads and persists a file from disk."""
    fixture_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    case = ingest_fixture_file(db_session, fixture_path)

    assert case.case_id == "CASE-2026-001"
    assert case.status == "NEW"

    # Non-existent file should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        ingest_fixture_file(db_session, "non_existent_file.json")
