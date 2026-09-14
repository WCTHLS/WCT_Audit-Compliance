"""
End-to-End Integration Test Suite for WCT Case Management Workflow.

Validates the complete lifecycle:
1. Ingestion of 'case.created' event via Kafka Consumer logic.
2. Database persistence with 72-hour SLA tracking and JSONB evidence pointers.
3. REST API querying (GET /cases, GET /cases/{id}) with JWT Bearer authentication.
4. Shared Library Evidence Resolution (EvidenceLookupClient) for clinical EHR notes,
   SHAP risk factor waterfalls, peer distributions, and claim flags.
5. Auditor Workflow & Decision Updates (PATCH /cases/{id}) to transition states
   (NEW -> READY_FOR_REVIEW -> CLOSED) and record final audit determinations.
6. RBAC & validation enforcement across the workflow.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.models import Case
from src.main import app
from src.consumer import process_case_created_event
from auth_middleware.test_tokens import get_test_token
from evidence_lookup import EvidenceLookupClient
from event_contracts import CaseStatusEnum, AuditDecisionEnum, SlaTypeEnum

# Path to mock-data fixtures
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


@pytest.fixture
def full_flow_context():
    """
    Creates an isolated in-memory SQLite environment shared across
    both consumer ingestion and FastAPI TestClient.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db_session = TestingSessionLocal()
    with TestClient(app) as test_client:
        yield {
            "db": db_session,
            "client": test_client,
            "evidence_client": EvidenceLookupClient(base_dir=MOCK_DATA_DIR),
        }

    db_session.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_full_case_001_lifecycle(full_flow_context):
    """
    Full end-to-end lifecycle for CASE-2026-001 (High-volume outlier billing).
    Steps:
      1. Ingest event fixture via consumer -> DB.
      2. Verify SLA deadline calculation (+72 hours).
      3. Query case via API (GET /cases/CASE-2026-001).
      4. Resolve all evidence pointers using EvidenceLookupClient.
      5. Auditor transitions case to READY_FOR_REVIEW.
      6. Auditor reviews resolved evidence & submits final UPHOLD decision.
      7. Verify case status CLOSED with full audit trail.
    """
    db = full_flow_context["db"]
    client = full_flow_context["client"]
    evidence_client = full_flow_context["evidence_client"]

    auditor_token = get_test_token("auditor")
    auth_headers = {"Authorization": f"Bearer {auditor_token}"}

    # 1. Ingestion: Process case.created event
    event_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(event_path, encoding="utf-8") as f:
        event_payload = json.load(f)

    created_case = process_case_created_event(db, event_payload)
    assert created_case.case_id == "CASE-2026-001"
    assert created_case.status == CaseStatusEnum.NEW.value
    assert created_case.risk_score == 850

    # 2. SLA Clock Verification: Check 72h window from event timestamp
    event_ts = datetime.fromisoformat(event_payload["timestamp"].replace("Z", "+00:00"))
    expected_sla_deadline = event_ts + timedelta(hours=72)
    assert created_case.sla_due_at.replace(tzinfo=timezone.utc) == expected_sla_deadline
    assert created_case.sla_breached is False
    assert created_case.sla_type == SlaTypeEnum.INITIAL_REVIEW.value

    # 3. REST API Query: Fetch case via GET /cases/CASE-2026-001
    get_resp = client.get("/cases/CASE-2026-001", headers=auth_headers)
    assert get_resp.status_code == 200
    case_data = get_resp.json()
    assert case_data["case_id"] == "CASE-2026-001"
    assert case_data["status"] == "NEW"
    assert case_data["doctor_name"] == "Dr. Robert Vance, MD"
    assert float(case_data["total_claim_amount"]) == 3250.00
    assert "evidence_pointers" in case_data

    # 4. Evidence Resolution: Use EvidenceLookupClient to resolve pointers
    pointers = case_data["evidence_pointers"]
    bundle = evidence_client.resolve_all(pointers)

    # Validate clinical evidence details
    assert bundle.clinical_evidence is not None
    assert bundle.clinical_evidence.patient_demographics.patient_id == "PAT-44910"
    diagnosis_codes = [d.code for d in bundle.clinical_evidence.diagnoses]
    assert "I25.10" in diagnosis_codes
    assert "I10" in diagnosis_codes
    assert len(bundle.clinical_evidence.claim_lines) >= 1

    # Validate risk factors
    assert bundle.risk_factors is not None
    assert len(bundle.risk_factors.risk_factors) > 0

    # Validate peer comparison metrics
    assert bundle.peer_comparison_detail is not None
    assert bundle.peer_comparison_detail.statistics.computed_percentile == 98.2
    assert bundle.peer_comparison_detail.specialty == "Interventional Cardiology"

    # Validate claim flags
    assert bundle.claim_flags is not None
    assert bundle.claim_flags.total_flags == 2
    flag_codes = [flg.flag_code for flg in bundle.claim_flags.flags]
    assert "PI-EDIT-MOD25-UNBUNDLED" in flag_codes
    assert "PI-EDIT-E&M-UPCODING" in flag_codes

    # 5. Auditor Workflow: Transition to READY_FOR_REVIEW & assign auditor
    patch_review_resp = client.patch(
        "/cases/CASE-2026-001",
        json={"status": "READY_FOR_REVIEW", "assigned_auditor": "auditor.jenkins@wct-payer.com"},
        headers=auth_headers,
    )
    assert patch_review_resp.status_code == 200
    review_data = patch_review_resp.json()
    assert review_data["status"] == "READY_FOR_REVIEW"
    assert review_data["assigned_auditor"] == "auditor.jenkins@wct-payer.com"

    # 6. Auditor Decision: Submit final UPHOLD determination
    decision_payload = {
        "status": "CLOSED",
        "decision": "UPHOLD",
        "decision_rationale": (
            "Clinical notes and peer comparison (98.2 percentile) confirm severe unbundling "
            "and modifier 25 anomaly. Claim denied in full per CMS policy."
        ),
        "regulatory_basis": "CMS NCCI Policy Manual Chapter 11, Section B",
    }
    decision_resp = client.patch(
        "/cases/CASE-2026-001",
        json=decision_payload,
        headers=auth_headers,
    )
    assert decision_resp.status_code == 200
    closed_data = decision_resp.json()
    assert closed_data["status"] == "CLOSED"
    assert closed_data["decision"] == "UPHOLD"
    assert closed_data["decision_rationale"] == decision_payload["decision_rationale"]
    assert closed_data["regulatory_basis"] == decision_payload["regulatory_basis"]

    # 7. Verification: Final GET call to ensure database persistence
    final_get = client.get("/cases/CASE-2026-001", headers=auth_headers)
    assert final_get.status_code == 200
    final_data = final_get.json()
    assert final_data["status"] == "CLOSED"
    assert final_data["decision"] == "UPHOLD"
    assert final_data["assigned_auditor"] == "auditor.jenkins@wct-payer.com"


def test_full_case_002_drg_upcoding_lifecycle(full_flow_context):
    """
    Full end-to-end lifecycle for CASE-2026-002 (Inpatient DRG Upcoding).
    Steps:
      1. Ingest DRG upcoding event fixture.
      2. Verify DRG case in DB with high risk score (920).
      3. Query case via API.
      4. Resolve evidence bundle (clinical notes, SHAP, peer comparison).
      5. Auditor transitions case to CLOSED with REVERSE decision.
    """
    db = full_flow_context["db"]
    client = full_flow_context["client"]
    evidence_client = full_flow_context["evidence_client"]

    auditor_token = get_test_token("auditor")
    auth_headers = {"Authorization": f"Bearer {auditor_token}"}

    # 1. Ingest Case 2
    event_path = MOCK_DATA_DIR / "fwa-mock" / "case_002_event.json"
    with open(event_path, encoding="utf-8") as f:
        event_payload = json.load(f)

    created_case = process_case_created_event(db, event_payload)
    assert created_case.case_id == "CASE-2026-002"
    assert created_case.risk_score == 920
    assert "DRG 469" in created_case.flagged_reason

    # 2. Query via API
    resp = client.get("/cases/CASE-2026-002", headers=auth_headers)
    assert resp.status_code == 200
    case_json = resp.json()
    assert case_json["doctor_name"] == "Dr. Arthur Pendelton, MD"
    assert float(case_json["total_claim_amount"]) == 28500.00

    # 3. Resolve evidence pointers
    bundle = evidence_client.resolve_all(case_json["evidence_pointers"])
    assert bundle.clinical_evidence.patient_demographics.patient_id == "PAT-78192"
    assert bundle.peer_comparison_detail.statistics.computed_percentile == 99.1

    # 4. Auditor closes case with decision
    decision_payload = {
        "status": "CLOSED",
        "decision": "REVERSE",
        "decision_rationale": (
            "Secondary MCC (I16.0) was documented in bedside monitoring logs during post-op recovery. "
            "DRG 469 assignment is substantiated. Overturning fraud flag."
        ),
        "regulatory_basis": "CMS ICD-10-CM Official Guidelines for Coding and Reporting (FY2026)",
    }
    decision_resp = client.patch(
        "/cases/CASE-2026-002",
        json=decision_payload,
        headers=auth_headers,
    )
    assert decision_resp.status_code == 200
    res = decision_resp.json()
    assert res["status"] == "CLOSED"
    assert res["decision"] == "REVERSE"


def test_full_flow_security_and_validation(full_flow_context):
    """
    Verify security and input validation across the end-to-end flow:
    - Missing token is rejected with 401 Unauthorized.
    - Malformed token is rejected with 401 Unauthorized.
    - Decision update without required rationale fails with 422 Unprocessable Entity.
    """
    db = full_flow_context["db"]
    client = full_flow_context["client"]

    # Ingest case
    event_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(event_path, encoding="utf-8") as f:
        event_payload = json.load(f)
    process_case_created_event(db, event_payload)

    # 1. Unauthenticated request -> 401
    unauth_resp = client.patch(
        "/cases/CASE-2026-001",
        json={"status": "CLOSED", "decision": "UPHOLD", "decision_rationale": "Valid notes"},
    )
    assert unauth_resp.status_code == 401

    # 2. Malformed token -> 401
    bad_token_resp = client.patch(
        "/cases/CASE-2026-001",
        json={"status": "CLOSED", "decision": "UPHOLD", "decision_rationale": "Valid notes"},
        headers={"Authorization": "Bearer invalid.token.signature"},
    )
    assert bad_token_resp.status_code == 401

    # 3. Decision recorded without rationale -> 422 Validation Error
    auditor_token = get_test_token("auditor")
    invalid_decision_resp = client.patch(
        "/cases/CASE-2026-001",
        json={"decision": "UPHOLD", "decision_rationale": ""},
        headers={"Authorization": f"Bearer {auditor_token}"},
    )
    assert invalid_decision_resp.status_code == 422
