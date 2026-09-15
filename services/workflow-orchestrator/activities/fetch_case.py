"""
Temporal Activity: fetch_case_activity.
Fetches full case details and evidence pointers from Case Management Service API.
"""

import json
import logging
from pathlib import Path
import httpx
from temporalio import activity

from src.config import settings
from activities.params import FetchCaseResult

logger = logging.getLogger("activity.fetch_case")


@activity.defn(name="fetch_case_activity")
async def fetch_case_activity(case_id: str) -> FetchCaseResult:
    """
    Fetches case data from Case Management Service (GET /cases/{id}).
    Falls back to mock fixture data if API service is unreachable.
    """
    url = f"{settings.CASE_MANAGEMENT_URL}/cases/{case_id}"
    activity.logger.info(f"Fetching case details for case_id='{case_id}' from '{url}'...")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                activity.logger.info(f"Successfully retrieved case '{case_id}' from API.")
                return FetchCaseResult(
                    case_id=data.get("case_id", case_id),
                    claim_ref=data.get("claim_ref", ""),
                    status=data.get("status", "NEW"),
                    risk_score=data.get("risk_score", 0),
                    flagged_reason=data.get("flagged_reason", ""),
                    source_module=data.get("source_module", "fwa_detection"),
                    doctor_npi=data.get("doctor_npi", ""),
                    doctor_name=data.get("doctor_name", ""),
                    facility_npi=data.get("facility_npi", ""),
                    facility_name=data.get("facility_name", ""),
                    patient_id=data.get("patient_id"),
                    total_claim_amount=float(data.get("total_claim_amount", 0.0)),
                    evidence_pointers=data.get("evidence_pointers", {}),
                    found=True,
                )
    except Exception as exc:
        activity.logger.warning(
            f"Case Management API unavailable at '{url}' ({exc}). Falling back to local mock data."
        )

    # Fallback to local mock data fixtures
    current_dir = Path(__file__).resolve().parent
    repo_root = current_dir.parent.parent.parent
    mock_file = repo_root / "mock-data" / "fwa-mock" / "case_001_event.json"

    if mock_file.exists():
        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        activity.logger.info(f"Loaded case '{case_id}' from local mock fixture.")
        return FetchCaseResult(
            case_id=data.get("case_id", case_id),
            claim_ref=data.get("claim_ref", "CLM-99214-8841"),
            status="NEW",
            risk_score=data.get("risk_score", 850),
            flagged_reason=data.get("flagged_reason", ""),
            source_module=data.get("source_module", "fwa_detection"),
            doctor_npi=data.get("doctor_npi", "1093847562"),
            doctor_name=data.get("doctor_name", "Dr. Robert Vance, MD"),
            facility_npi=data.get("facility_npi", "1295847361"),
            facility_name=data.get("facility_name", "Memorial Health System"),
            patient_id=data.get("patient_id", "PAT-44910"),
            total_claim_amount=float(data.get("total_claim_amount", 3250.0)),
            evidence_pointers=data.get("evidence_pointers", {}),
            found=True,
        )

    return FetchCaseResult(
        case_id=case_id,
        claim_ref="UNKNOWN",
        status="NEW",
        risk_score=0,
        found=False,
        error="Case not found in API or mock fixtures.",
    )
