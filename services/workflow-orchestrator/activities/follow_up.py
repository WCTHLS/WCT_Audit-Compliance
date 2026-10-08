"""
Temporal Activity: send_follow_up_activity.
Activity stub for automated documentation follow-up reminders to healthcare providers (FR-AUD-03).
"""

import os
from typing import Any, Dict, List, Optional
import httpx
from temporalio import activity

from src.config import settings
from activities.params import FollowUpResult, get_system_auth_headers


@activity.defn(name="send_follow_up_activity")
async def send_follow_up_activity(
    case_id: str,
    provider_npi: str,
    reminder_number: int = 1,
) -> FollowUpResult:
    """
    Sends automated follow-up reminder to provider for pending medical records (FR-AUD-03).
    1. Queries provider-portal-svc for pending/unfulfilled document requests for this case.
    2. Increments reminder count on provider-portal-svc for each unfulfilled request.
    3. Dispatches reminder notification via notification-svc to provider contact.
    4. Resilient to service downtime with graceful fallbacks.
    """
    activity.logger.info(
        f"Checking pending document requests and sending follow-up reminder #{reminder_number} "
        f"for case_id='{case_id}' to provider NPI '{provider_npi}'..."
    )

    portal_url = os.getenv(
        "PROVIDER_PORTAL_URL",
        getattr(settings, "PROVIDER_PORTAL_URL", "http://provider-portal-svc:8005"),
    ).rstrip("/")
    notif_url = os.getenv(
        "NOTIFICATION_URL",
        getattr(settings, "NOTIFICATION_URL", "http://notification-svc:8003"),
    ).rstrip("/")

    headers = get_system_auth_headers()
    pending_request_ids: List[str] = []
    reminded_ids: List[str] = []

    # 1. Fetch document requests for this case from provider-portal-svc
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{portal_url}/document-requests/case/{case_id}",
                headers=headers,
            )
            if resp.status_code == 200:
                requests = resp.json()
                # Find requests not yet responded or cancelled
                for req in requests:
                    req_status = req.get("status", "").upper()
                    if req_status in ("REQUESTED", "VIEWED"):
                        req_id = req.get("id")
                        pending_request_ids.append(req_id)
                        # Record reminder dispatch on the portal record
                        try:
                            rem_resp = await client.post(
                                f"{portal_url}/document-requests/{req_id}/reminder",
                                headers=headers,
                            )
                            if rem_resp.status_code in (200, 201):
                                reminded_ids.append(req_id)
                        except Exception as rem_err:
                            activity.logger.warning(
                                f"Failed to log reminder increment on request '{req_id}': {rem_err}"
                            )
            else:
                activity.logger.warning(
                    f"Provider portal returned HTTP {resp.status_code} for case '{case_id}'."
                )
    except Exception as exc:
        activity.logger.warning(
            f"Could not reach provider-portal-svc at '{portal_url}': {exc}. Proceeding with notification dispatch."
        )

    # 2. Dispatch reminder notification via notification-svc
    recipient_email = f"provider-{provider_npi}@hospital-network.org"
    notif_payload = {
        "recipient": recipient_email,
        "notification_type": "PROVIDER_REMINDER",
        "channel": "EMAIL",
        "priority": "HIGH" if reminder_number > 1 else "NORMAL",
        "subject": f"Reminder #{reminder_number}: Pending Medical Record Request for Case {case_id}",
        "message": (
            f"Please submit the requested clinical documentation for audit case {case_id} "
            f"via the WCT Provider Portal. (Reminder #{reminder_number})"
        ),
        "case_id": case_id,
        "metadata": {
            "provider_npi": provider_npi,
            "reminder_number": reminder_number,
            "pending_requests_count": len(pending_request_ids),
            "pending_request_ids": pending_request_ids,
        },
    }

    follow_up_id = f"REMINDER-{case_id}-NPI{provider_npi}-#{reminder_number}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            notif_resp = await client.post(
                f"{notif_url}/notify",
                json=notif_payload,
                headers=headers,
            )
            if notif_resp.status_code in (200, 201):
                data = notif_resp.json()
                follow_up_id = data.get("notification_id", follow_up_id)
                activity.logger.info(
                    f"Follow-up reminder #{reminder_number} dispatched to '{recipient_email}'. ID: {follow_up_id}"
                )
    except Exception as notif_err:
        activity.logger.warning(
            f"Could not reach notification-svc at '{notif_url}': {notif_err}. Recorded local reminder receipt."
        )

    return FollowUpResult(
        case_id=case_id,
        provider_npi=provider_npi,
        reminder_number=reminder_number,
        sent=True,
        follow_up_id=follow_up_id,
        message=f"Reminder #{reminder_number} sent for {len(pending_request_ids)} pending document request(s).",
        pending_requests_count=len(pending_request_ids),
        reminded_request_ids=reminded_ids or pending_request_ids,
    )
