"""
Comprehensive API test suite for Provider Portal Service.
Tests document requests, read receipts, and provider response submissions.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_health_check(client: AsyncClient):
    """Verify health endpoint reports healthy status."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "provider-portal-svc"
    assert data["total_requests"] == 0


@pytest.mark.anyio
async def test_create_document_request(client: AsyncClient):
    """Verify auditor can create a new document request."""
    payload = {
        "case_id": "CASE-2026-001",
        "provider_npi": "1093847562",
        "provider_name": "Dr. Robert Vance, MD",
        "requested_documents": [
            "Operative Report for Date of Service 2026-08-10",
            "Signed Clinical Progress Note",
        ],
        "instructions": "Please provide signed clinical documentation supporting separate E&M Modifier 25.",
        "requested_by": "senior-auditor@wct-health.com",
    }

    resp = await client.post("/document-requests", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["id"].startswith("DOCREQ-")
    assert data["case_id"] == "CASE-2026-001"
    assert data["provider_npi"] == "1093847562"
    assert data["status"] == "REQUESTED"
    assert len(data["requested_documents"]) == 2
    assert data["read_at"] is None
    assert data["read_count"] == 0
    assert data["responded_at"] is None


@pytest.mark.anyio
async def test_create_request_validation_failure(client: AsyncClient):
    """Verify schema rejects invalid NPI or missing documents."""
    # NPI too short (must be 10 digits)
    bad_npi = {
        "case_id": "CASE-2026-001",
        "provider_npi": "123",
        "requested_documents": ["Chart Notes"],
    }
    resp = await client.post("/document-requests", json=bad_npi)
    assert resp.status_code == 422

    # Empty requested_documents list
    empty_docs = {
        "case_id": "CASE-2026-001",
        "provider_npi": "1093847562",
        "requested_documents": [],
    }
    resp2 = await client.post("/document-requests", json=empty_docs)
    assert resp2.status_code == 422


@pytest.mark.anyio
async def test_get_document_request_by_id(client: AsyncClient):
    """Verify retrieving document request by unique ID."""
    create_resp = await client.post(
        "/document-requests",
        json={
            "case_id": "CASE-2026-002",
            "provider_npi": "1295847361",
            "requested_documents": ["Itemized Billing Statement"],
        },
    )
    req_id = create_resp.json()["id"]

    get_resp = await client.get(f"/document-requests/{req_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == req_id
    assert get_resp.json()["case_id"] == "CASE-2026-002"

    # Non-existent ID
    bad_resp = await client.get("/document-requests/DOCREQ-999999-NOTFOUND")
    assert bad_resp.status_code == 404


@pytest.mark.anyio
async def test_list_requests_and_filter_by_case(client: AsyncClient):
    """Verify listing requests and filtering by case ID."""
    # Create 2 requests for CASE-001 and 1 for CASE-002
    await client.post(
        "/document-requests",
        json={"case_id": "CASE-2026-001", "provider_npi": "1093847562", "requested_documents": ["Doc 1"]},
    )
    await client.post(
        "/document-requests",
        json={"case_id": "CASE-2026-001", "provider_npi": "1093847562", "requested_documents": ["Doc 2"]},
    )
    await client.post(
        "/document-requests",
        json={"case_id": "CASE-2026-002", "provider_npi": "1295847361", "requested_documents": ["Doc 3"]},
    )

    # List all
    all_resp = await client.get("/document-requests")
    assert all_resp.status_code == 200
    data = all_resp.json()
    assert data["total"] == 3
    assert data["requested_count"] == 3

    # Filter by CASE-001
    case1_resp = await client.get("/document-requests/case/CASE-2026-001")
    assert case1_resp.status_code == 200
    assert len(case1_resp.json()) == 2

    # Filter by provider
    prov_resp = await client.get("/document-requests/provider/1093847562")
    assert prov_resp.status_code == 200
    assert len(prov_resp.json()) == 2


@pytest.mark.anyio
async def test_read_receipt_recording(client: AsyncClient):
    """Verify recording read receipts transitions status from REQUESTED to VIEWED."""
    create_resp = await client.post(
        "/document-requests",
        json={
            "case_id": "CASE-2026-001",
            "provider_npi": "1093847562",
            "requested_documents": ["Cardiology Consult Report"],
        },
    )
    req_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "REQUESTED"
    assert create_resp.json()["read_at"] is None

    # Provider opens/reads the request
    read_resp = await client.post(f"/document-requests/{req_id}/read")
    assert read_resp.status_code == 200
    read_data = read_resp.json()

    assert read_data["status"] == "VIEWED"
    assert read_data["read_at"] is not None
    assert read_data["read_count"] == 1
    first_read_timestamp = read_data["read_at"]

    # Provider re-opens/views again
    re_read_resp = await client.post(f"/document-requests/{req_id}/read")
    re_read_data = re_read_resp.json()
    assert re_read_data["status"] == "VIEWED"
    assert re_read_data["read_at"] == first_read_timestamp  # original read_at preserved
    assert re_read_data["read_count"] == 2


@pytest.mark.anyio
async def test_auto_mark_as_read_query_parameter(client: AsyncClient):
    """Verify GET /document-requests/{id}?mark_as_read=true records receipt."""
    create_resp = await client.post(
        "/document-requests",
        json={
            "case_id": "CASE-2026-003",
            "provider_npi": "1093847562",
            "requested_documents": ["Anesthesia Record"],
        },
    )
    req_id = create_resp.json()["id"]

    get_resp = await client.get(f"/document-requests/{req_id}?mark_as_read=true")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["status"] == "VIEWED"
    assert data["read_count"] == 1


@pytest.mark.anyio
async def test_provider_response_submission(client: AsyncClient):
    """Verify provider can submit documentation notes and attached files."""
    create_resp = await client.post(
        "/document-requests",
        json={
            "case_id": "CASE-2026-001",
            "provider_npi": "1093847562",
            "requested_documents": ["Signed Clinic Note"],
        },
    )
    req_id = create_resp.json()["id"]

    # Provider responds with notes and file references
    response_payload = {
        "response_notes": "Attached please find Dr. Vance's signed clinical notes documenting the distinct E&M evaluation.",
        "responded_by": "clinic-records@vancecardiology.com",
        "attachments": [
            {
                "filename": "clinical_note_20260810_signed.pdf",
                "file_type": "application/pdf",
                "file_size_bytes": 142850,
                "storage_uri": "s3://wct-provider-documents/cases/CASE-2026-001/clinical_note_20260810_signed.pdf",
            }
        ],
    }

    respond_resp = await client.post(f"/document-requests/{req_id}/respond", json=response_payload)
    assert respond_resp.status_code == 200
    data = respond_resp.json()

    assert data["status"] == "RESPONDED"
    assert "distinct E&M evaluation" in data["response_notes"]
    assert data["responded_by"] == "clinic-records@vancecardiology.com"
    assert data["responded_at"] is not None
    assert len(data["attachments"]) == 1
    assert data["attachments"][0]["filename"] == "clinical_note_20260810_signed.pdf"


@pytest.mark.anyio
async def test_follow_up_reminder_and_cancel_lifecycle(client: AsyncClient):
    """Verify follow-up reminder tracking and cancellation."""
    create_resp = await client.post(
        "/document-requests",
        json={
            "case_id": "CASE-2026-004",
            "provider_npi": "1093847562",
            "requested_documents": ["Lab Results"],
        },
    )
    req_id = create_resp.json()["id"]

    # Record reminder #1
    rem_resp1 = await client.post(f"/document-requests/{req_id}/reminder")
    assert rem_resp1.status_code == 200
    assert rem_resp1.json()["reminders_sent"] == 1

    # Record reminder #2
    rem_resp2 = await client.post(f"/document-requests/{req_id}/reminder")
    assert rem_resp2.status_code == 200
    assert rem_resp2.json()["reminders_sent"] == 2

    # Cancel request
    cancel_resp = await client.post(f"/document-requests/{req_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Attempting to respond to cancelled request is rejected
    reject_resp = await client.post(
        f"/document-requests/{req_id}/respond",
        json={"response_notes": "Trying to respond anyway"},
    )
    assert reject_resp.status_code == 400
