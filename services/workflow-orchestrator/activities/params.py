"""
Data models and parameters for Temporal Activities in CaseAuditWorkflow.
"""

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional


def get_system_auth_headers() -> Dict[str, str]:
    """Generates standard JWT Bearer headers for inter-service communication."""
    secret = os.getenv("JWT_SECRET_KEY", "wct-audit-compliance-dev-secret-key-2026")
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "workflow-orchestrator",
        "role": "AUDITOR",
        "name": "System Orchestrator",
        "email": "orchestrator@wct-health.com",
        "iat": int(time.time()),
        "exp": int(time.time() + 86400 * 365),
    }

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

    hdr_b64 = b64url(json.dumps(header).encode("utf-8"))
    pay_b64 = b64url(json.dumps(payload).encode("utf-8"))
    signing_input = f"{hdr_b64}.{pay_b64}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = b64url(sig)
    token = f"{hdr_b64}.{pay_b64}.{sig_b64}"
    return {
        "Authorization": f"Bearer {token}",
        "X-Internal-Service": "workflow-orchestrator",
    }


@dataclass
class FetchCaseResult:
    """Result returned by fetch_case_activity."""
    case_id: str
    claim_ref: str
    status: str
    risk_score: int
    flagged_reason: str = ""
    source_module: str = "fwa_detection"
    doctor_npi: str = ""
    doctor_name: str = ""
    facility_npi: str = ""
    facility_name: str = ""
    patient_id: Optional[str] = None
    total_claim_amount: float = 0.0
    evidence_pointers: Dict[str, Any] = field(default_factory=dict)
    found: bool = True
    error: Optional[str] = None


@dataclass
class SummarizeResult:
    """Result returned by summarize_case_activity."""
    case_id: str
    clinical_summary: str
    risk_factors_summary: str
    peer_comparison_narrative: str
    confidence_score: float = 0.95
    model_version: str = "gpt-4o-stub-v1"


@dataclass
class ScreeningResult:
    """Result returned by screen_exclusions_activity."""
    doctor_npi: str
    doctor_name: str
    is_excluded: bool = False
    exclusion_type: Optional[str] = None
    exclusion_date: Optional[str] = None
    sanction_authority: str = "OIG LEIE"
    matched_records_count: int = 0
    details: str = "No federal exclusion records found."


@dataclass
class NotificationResult:
    """Result returned by notify_auditor_activity."""
    recipient: str
    notification_type: str
    case_id: str
    sent: bool = True
    notification_id: str = "NOTIF-MOCK-001"
    delivered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class FollowUpResult:
    """Result returned by send_follow_up_activity."""
    case_id: str
    provider_npi: str
    reminder_number: int
    sent: bool = True
    follow_up_id: str = "FOLLOWUP-MOCK-001"
    message: str = "Automated document request reminder sent."
