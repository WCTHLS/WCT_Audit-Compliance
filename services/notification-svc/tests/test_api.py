"""
API integration tests for WCT Notification Service.
Validates all endpoints, payload schemas, error conditions, and audit queries.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Verifies that /health reports healthy status and includes telemetry."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "notification-svc"
    assert "console-logger" in data["active_providers"]
    assert data["total_dispatched"] == 0


def test_dispatch_sla_breach_warning(client: TestClient):
    """Verifies impending SLA breach warning notification."""
    payload = {
        "recipient": "auditor.smith@wct-health.com",
        "notification_type": "SLA_BREACH_WARNING",
        "channel": "EMAIL",
        "priority": "HIGH",
        "subject": "Impending SLA Breach: CASE-2026-001",
        "message": "Only 6 hours remain before the 72-hour regulatory resolution deadline.",
        "case_id": "CASE-2026-001",
        "metadata": {"hours_remaining": 6, "risk_score": 850},
    }
    response = client.post("/notify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["notification_id"].startswith("NOTIF-")
    assert data["status"] == "DELIVERED"
    assert data["recipient"] == "auditor.smith@wct-health.com"
    assert data["notification_type"] == "SLA_BREACH_WARNING"
    assert data["case_id"] == "CASE-2026-001"
    assert data["metadata"]["hours_remaining"] == 6


def test_dispatch_document_request_reminder(client: TestClient):
    """Verifies automated provider document request reminder (FR-AUD-03)."""
    payload = {
        "recipient": "1093847562",  # Provider NPI
        "notification_type": "DOCUMENT_REQUEST_REMINDER",
        "channel": "EMAIL",
        "priority": "NORMAL",
        "subject": "Reminder #1: Documentation Request Pending for Claim CLM-2026-8841",
        "message": "Please submit operative report and itemized billing within 24 hours.",
        "case_id": "CASE-2026-001",
        "metadata": {"provider_npi": "1093847562", "reminder_number": 1},
    }
    response = client.post("/notify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "DELIVERED"
    assert data["notification_type"] == "DOCUMENT_REQUEST_REMINDER"
    assert data["metadata"]["reminder_number"] == 1


def test_dispatch_auditor_escalation(client: TestClient):
    """Verifies escalation sent when provider ignores follow-up reminders."""
    payload = {
        "recipient": "lead-compliance-officer@wct-health.com",
        "notification_type": "AUDITOR_ESCALATION",
        "channel": "IN_APP",
        "priority": "URGENT",
        "subject": "Case CASE-2026-001: Escalation for Missing Documentation",
        "message": "Provider failed to respond to 2 automated follow-up reminders.",
        "case_id": "CASE-2026-001",
        "metadata": {"reminders_sent": 2, "provider_npi": "1093847562"},
    }
    response = client.post("/notify", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "DELIVERED"
    assert data["notification_type"] == "AUDITOR_ESCALATION"


def test_invalid_payload_returns_422(client: TestClient):
    """Verifies that invalid requests are rejected with 422 Unprocessable Entity."""
    # Missing required message and subject
    payload = {
        "recipient": "auditor@wct.com",
        "notification_type": "SLA_BREACH",
    }
    response = client.post("/notify", json=payload)
    assert response.status_code == 422


def test_list_and_filter_notifications(client: TestClient):
    """Verifies querying and filtering notifications by case_id and type."""
    # Send 2 notifications for case 1 and 1 for case 2
    for notif_type in ["SLA_BREACH_WARNING", "AUDITOR_ESCALATION"]:
        client.post(
            "/notify",
            json={
                "recipient": "auditor@wct.com",
                "notification_type": notif_type,
                "subject": f"Test {notif_type}",
                "message": "Test message",
                "case_id": "CASE-2026-001",
            },
        )
    client.post(
        "/notify",
        json={
            "recipient": "auditor2@wct.com",
            "notification_type": "CASE_ASSIGNMENT",
            "subject": "New Case",
            "message": "Assigned",
            "case_id": "CASE-2026-002",
        },
    )

    # Filter by case_id
    res_case1 = client.get("/notifications?case_id=CASE-2026-001")
    assert res_case1.status_code == 200
    assert len(res_case1.json()) == 2

    # Filter by notification_type
    res_type = client.get("/notifications?notification_type=CASE_ASSIGNMENT")
    assert res_type.status_code == 200
    assert len(res_type.json()) == 1
    assert res_type.json()[0]["case_id"] == "CASE-2026-002"


def test_get_notification_by_id_and_not_found(client: TestClient):
    """Verifies fetching a specific notification by ID and 404 behavior."""
    resp = client.post(
        "/notify",
        json={
            "recipient": "auditor@wct.com",
            "notification_type": "SYSTEM_ALERT",
            "subject": "System Notice",
            "message": "Maintenance tonight",
        },
    )
    notif_id = resp.json()["notification_id"]

    # Fetch existing
    get_res = client.get(f"/notifications/{notif_id}")
    assert get_res.status_code == 200
    assert get_res.json()["notification_id"] == notif_id

    # Fetch non-existent
    bad_res = client.get("/notifications/NOTIF-DOES-NOT-EXIST")
    assert bad_res.status_code == 404
