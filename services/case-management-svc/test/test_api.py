"""
Integration and API test suite for Case Management Service CRUD endpoints.
Tests POST /cases, GET /cases, GET /cases/{id}, PATCH /cases/{id},
authentication checks, validation error handling, and decision workflows.
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from auth_middleware.test_tokens import get_test_token

# Path to mock-data fixtures
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


@pytest.fixture
def client_and_db():
    """
    Creates an isolated in-memory SQLite database and test client for each API test.
    Overrides the get_db dependency.
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
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def auditor_auth_headers():
    """Provides valid Bearer Authorization header for auditor profile."""
    token = get_test_token("auditor")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def system_auth_headers():
    """Provides valid Bearer Authorization header for system orchestrator profile."""
    token = get_test_token("system")
    return {"Authorization": f"Bearer {token}"}


def test_system_root_and_health(client_and_db):
    """Verify GET / and GET /health work without requiring authentication."""
    res_root = client_and_db.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["service"] == "case-management-svc"

    res_health = client_and_db.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"


def test_auth_guard_enforcement(client_and_db):
    """Verify that case endpoints reject unauthenticated or malformed requests with 401."""
    # Missing header
    res_no_auth = client_and_db.get("/cases")
    assert res_no_auth.status_code == 401
    assert "Missing Authorization header" in res_no_auth.json()["detail"]

    # Invalid Bearer format
    res_bad_format = client_and_db.get("/cases", headers={"Authorization": "InvalidToken"})
    assert res_bad_format.status_code == 401

    # Invalid token content
    res_invalid_jwt = client_and_db.get("/cases", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert res_invalid_jwt.status_code == 401


def test_create_and_get_case(client_and_db, auditor_auth_headers):
    """Verify POST /cases creates a new case and GET /cases/{id} retrieves it."""
    case_001_path = MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json"
    with open(case_001_path, encoding="utf-8") as f:
        payload = json.load(f)

    # 1. Create Case
    res_create = client_and_db.post("/cases", json=payload, headers=auditor_auth_headers)
    assert res_create.status_code == 201
    created_data = res_create.json()
    assert created_data["case_id"] == "CASE-2026-001"
    assert created_data["claim_ref"] == "CLM-99214-8841"
    assert created_data["status"] == "NEW"
    assert created_data["risk_score"] == 850
    assert created_data["doctor_name"] == "Dr. Robert Vance, MD"
    assert "peer_comparison" in created_data["evidence_pointers"]
    assert created_data["sla_breached"] is False
    assert created_data["sla_due_at"] is not None

    # 2. Duplicate Create Conflict
    res_duplicate = client_and_db.post("/cases", json=payload, headers=auditor_auth_headers)
    assert res_duplicate.status_code == 409
    assert "already exists" in res_duplicate.json()["detail"]

    # 3. Get Case By ID
    res_get = client_and_db.get("/cases/CASE-2026-001", headers=auditor_auth_headers)
    assert res_get.status_code == 200
    assert res_get.json()["case_id"] == "CASE-2026-001"

    # 4. Get Non-existent Case
    res_404 = client_and_db.get("/cases/NON-EXISTENT", headers=auditor_auth_headers)
    assert res_404.status_code == 404


def test_list_cases_filtering_and_pagination(client_and_db, auditor_auth_headers):
    """Verify GET /cases supports query filtering (status, source_module) and pagination."""
    # Insert Case 1
    with open(MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json", encoding="utf-8") as f:
        c1 = json.load(f)
    client_and_db.post("/cases", json=c1, headers=auditor_auth_headers)

    # Insert Case 2
    with open(MOCK_DATA_DIR / "fwa-mock" / "case_002_event.json", encoding="utf-8") as f:
        c2 = json.load(f)
    client_and_db.post("/cases", json=c2, headers=auditor_auth_headers)

    # 1. List all
    res_all = client_and_db.get("/cases", headers=auditor_auth_headers)
    assert res_all.status_code == 200
    data = res_all.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # 2. Pagination test
    res_page = client_and_db.get("/cases?skip=1&limit=1", headers=auditor_auth_headers)
    assert res_page.status_code == 200
    data_page = res_page.json()
    assert data_page["total"] == 2
    assert len(data_page["items"]) == 1

    # 3. Filter by status
    res_filter_status = client_and_db.get("/cases?status=NEW", headers=auditor_auth_headers)
    assert res_filter_status.status_code == 200
    assert res_filter_status.json()["total"] == 2

    res_filter_none = client_and_db.get("/cases?status=CLOSED", headers=auditor_auth_headers)
    assert res_filter_none.status_code == 200
    assert res_filter_none.json()["total"] == 0


def test_patch_case_workflow_and_decision(client_and_db, auditor_auth_headers):
    """Verify PATCH /cases/{id} for auditor assignment, status transitions, and decision recording."""
    with open(MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json", encoding="utf-8") as f:
        payload = json.load(f)
    client_and_db.post("/cases", json=payload, headers=auditor_auth_headers)

    # 1. Assign Auditor and update status to READY_FOR_REVIEW
    res_assign = client_and_db.patch(
        "/cases/CASE-2026-001",
        json={"assigned_auditor": "auditor.jenkins@wct-payer.com", "status": "READY_FOR_REVIEW"},
        headers=auditor_auth_headers,
    )
    assert res_assign.status_code == 200
    assigned_case = res_assign.json()
    assert assigned_case["assigned_auditor"] == "auditor.jenkins@wct-payer.com"
    assert assigned_case["status"] == "READY_FOR_REVIEW"

    # 2. Attempt decision recording without rationale (should fail 422)
    res_invalid_dec = client_and_db.patch(
        "/cases/CASE-2026-001",
        json={"decision": "UPHOLD", "decision_rationale": ""},
        headers=auditor_auth_headers,
    )
    assert res_invalid_dec.status_code == 422

    # 3. Record valid decision with regulatory citation
    decision_payload = {
        "decision": "UPHOLD",
        "decision_rationale": "Modifier 25 unsupported: no separate E&M service documented.",
        "regulatory_basis": "CMS NCCI Policy Manual Chapter 11, Section B",
    }
    res_dec = client_and_db.patch(
        "/cases/CASE-2026-001",
        json=decision_payload,
        headers=auditor_auth_headers,
    )
    assert res_dec.status_code == 200
    decided_case = res_dec.json()
    assert decided_case["decision"] == "UPHOLD"
    assert decided_case["decision_rationale"] == "Modifier 25 unsupported: no separate E&M service documented."
    assert "CMS NCCI" in decided_case["regulatory_basis"]
    assert decided_case["status"] == "DECISION_RECORDED"
    assert decided_case["decided_by"] == "auditor.jenkins@wct-payer.com"
    assert decided_case["decided_at"] is not None
