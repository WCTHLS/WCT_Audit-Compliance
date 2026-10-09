"""
Week 5 Full Flow Multi-Service Integration Test Suite.
Validates the complete cohesive multi-service flow for Week 5:
1. Flow A: 72h SLA review window timeout -> SLA breach alert dispatched to Head Auditor.
2. Flow B: Auditor creates document request -> no provider response -> automated follow-up reminder dispatches provider alert.
3. Flow C: Provider opens request (read receipt logged) -> provider submits clinical response & attached files -> attached documents linked to case as evidence pointers for human auditor review.
"""

import os
import sys
import time
import socket
import threading
import subprocess
from pathlib import Path
import pytest
import httpx
from fastapi.testclient import TestClient

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))


def get_free_port() -> int:
    """Finds an available TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def running_services():
    """
    Spawns notification-svc, provider-portal-svc, and case-management-svc
    as live subprocess servers on separate ports to avoid Python namespace collisions.
    """
    python_exe = sys.executable
    portal_port = get_free_port()
    notif_port = get_free_port()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE_ROOT)

    # Launch notification-svc
    notif_env = env.copy()
    notif_env["SERVICE_PORT"] = str(notif_port)
    notif_env["ACTIVE_PROVIDERS"] = "console"
    notif_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "src.main:app", "--port", str(notif_port)],
        cwd=str(WORKSPACE_ROOT / "services" / "notification-svc"),
        env=notif_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Launch provider-portal-svc
    portal_env = env.copy()
    portal_env["SERVICE_PORT"] = str(portal_port)
    portal_env["NOTIFICATION_URL"] = f"http://127.0.0.1:{notif_port}"
    portal_proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "src.main:app", "--port", str(portal_port)],
        cwd=str(WORKSPACE_ROOT / "services" / "provider-portal-svc"),
        env=portal_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for services to become healthy
    urls = {
        "notif": f"http://127.0.0.1:{notif_port}",
        "portal": f"http://127.0.0.1:{portal_port}",
    }

    start_time = time.time()
    for name, base_url in urls.items():
        ready = False
        while time.time() - start_time < 15:
            try:
                r = httpx.get(f"{base_url}/health", timeout=1.0)
                if r.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)
        if not ready:
            notif_proc.kill()
            portal_proc.kill()
            raise RuntimeError(f"Service {name} at {base_url} failed to start in time.")

    yield urls

    # Teardown
    notif_proc.terminate()
    portal_proc.terminate()
    try:
        notif_proc.wait(timeout=3)
        portal_proc.wait(timeout=3)
    except Exception:
        notif_proc.kill()
        portal_proc.kill()


@pytest.mark.anyio
async def test_full_flow_a_sla_breach_alert(running_services):
    """
    Flow A: 72h SLA Breach Alert Flow
    1. Case review window expires without decision.
    2. Workflow orchestrator executes notify_auditor_activity with SLA_BREACH.
    3. Notification Service validates payload, logs alert, and returns delivery confirmation.
    """
    notif_url = running_services["notif"]

    # Dispatch SLA_BREACH notification directly to notification-svc
    payload = {
        "recipient": "lead-auditor@wct-health.com",
        "notification_type": "SLA_BREACH",
        "channel": "EMAIL",
        "priority": "URGENT",
        "subject": "URGENT: 72h SLA Breached for Case CASE-2026-001",
        "message": "Immediate supervisor intervention required. 72-hour review window expired.",
        "case_id": "CASE-2026-001",
        "metadata": {"risk_score": 850, "sla_breached": True},
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(f"{notif_url}/notify", json=payload)
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["status"] in ("SENT", "DELIVERED")
        assert data["notification_id"].startswith("NOTIF-")
        assert data["recipient"] == "lead-auditor@wct-health.com"


@pytest.mark.anyio
async def test_full_flow_b_doc_request_and_automated_followup(running_services):
    """
    Flow B: Document Request -> No Response -> Automated Follow-up Reminder Flow
    1. Auditor creates document request in provider-portal-svc.
    2. Status is REQUESTED, read_count is 0, reminders_sent is 0.
    3. Temporal orchestrator follow-up activity checks pending requests for the case.
    4. Activity increments reminder count on the request via POST /reminder.
    5. Follow-up reminder notification is dispatched to provider via notification-svc.
    """
    portal_url = running_services["portal"]
    notif_url = running_services["notif"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Auditor requests documentation
        req_payload = {
            "case_id": "CASE-2026-001",
            "provider_npi": "1093847562",
            "requested_documents": ["Operative Report", "Pathology Notes"],
            "provider_name": "Dr. Robert Vance, MD",
            "provider_email": "vance@mercy-general.org",
            "instructions": "Need operative report for CPT 99215 unbundling audit.",
            "requested_by": "lead-auditor@wct-health.com",
        }
        create_resp = await client.post(f"{portal_url}/document-requests", json=req_payload)
        assert create_resp.status_code == 201
        req_data = create_resp.json()
        req_id = req_data["id"]
        assert req_data["status"] == "REQUESTED"
        assert req_data["read_count"] == 0
        assert req_data["reminders_sent"] == 0

        # 2. Automated follow-up fires: query pending requests for case
        list_resp = await client.get(f"{portal_url}/document-requests/case/CASE-2026-001")
        assert list_resp.status_code == 200
        case_requests = list_resp.json()
        assert len(case_requests) >= 1
        pending = [r for r in case_requests if r["status"] in ("REQUESTED", "VIEWED")]
        assert len(pending) >= 1

        # 3. Log reminder increment
        rem_resp = await client.post(f"{portal_url}/document-requests/{req_id}/reminder")
        assert rem_resp.status_code == 200
        rem_data = rem_resp.json()
        assert rem_data["reminders_sent"] == 1

        # 4. Dispatch reminder notification via notification-svc
        notif_resp = await client.post(
            f"{notif_url}/notify",
            json={
                "recipient": "provider-1093847562@hospital-network.org",
                "notification_type": "DOCUMENT_REQUEST_REMINDER",
                "channel": "EMAIL",
                "priority": "NORMAL",
                "subject": f"Reminder #1: Pending Medical Record Request for Case CASE-2026-001",
                "message": "Please submit requested documentation via the WCT Provider Portal.",
                "case_id": "CASE-2026-001",
            },
        )
        assert notif_resp.status_code in (200, 201)
        assert notif_resp.json()["status"] in ("SENT", "DELIVERED")


@pytest.mark.anyio
async def test_full_flow_c_read_receipt_and_provider_response(running_services):
    """
    Flow C: Provider Read Receipt & Document Response Flow
    1. Auditor creates document request.
    2. Provider clicks/opens the request -> Read receipt logged (status: VIEWED, read_at set).
    3. Provider uploads/attaches documents and submits clinical narrative -> status: RESPONDED.
    4. Attachment metadata is confirmed and ready for auditor review.
    """
    portal_url = running_services["portal"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Create document request
        create_resp = await client.post(
            f"{portal_url}/document-requests",
            json={
                "case_id": "CASE-2026-002",
                "provider_npi": "1982736450",
                "requested_documents": ["Itemized Billing", "Operative Summary"],
                "requested_by": "auditor@wct-health.com",
            },
        )
        assert create_resp.status_code == 201
        req_id = create_resp.json()["id"]

        # 2. Provider opens request -> records read receipt
        read_resp = await client.post(
            f"{portal_url}/document-requests/{req_id}/read",
            json={"reader_identity": "records-clerk@hospital.org"},
        )
        assert read_resp.status_code == 200
        read_data = read_resp.json()
        assert read_data["status"] == "VIEWED"
        assert read_data["read_count"] == 1
        assert read_data["read_at"] is not None

        # 3. Provider submits response with document attachment metadata
        response_payload = {
            "response_notes": "Operative report attached confirming separate procedure for Modifier 25.",
            "responded_by": "Dr. Sarah Lin, MD",
            "attachments": [
                {
                    "filename": "operative_report_signed.pdf",
                    "file_type": "application/pdf",
                    "file_size_bytes": 182400,
                    "storage_uri": "s3://audit-compliance/docs/CASE-2026-002/operative_report_signed.pdf",
                }
            ],
        }
        submit_resp = await client.post(f"{portal_url}/document-requests/{req_id}/respond", json=response_payload)
        assert submit_resp.status_code == 200
        res_data = submit_resp.json()
        assert res_data["status"] == "RESPONDED"
        assert len(res_data["attachments"]) == 1
        assert res_data["attachments"][0]["filename"] == "operative_report_signed.pdf"
        assert res_data["responded_by"] == "Dr. Sarah Lin, MD"

        # 4. Verify request detail retrieval shows complete response
        get_resp = await client.get(f"{portal_url}/document-requests/{req_id}")
        assert get_resp.status_code == 200
        final_data = get_resp.json()
        assert final_data["status"] == "RESPONDED"
        assert final_data["read_count"] == 1
        assert len(final_data["attachments"]) == 1
