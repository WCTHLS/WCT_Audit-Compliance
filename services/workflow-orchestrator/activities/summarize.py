"""
Temporal Activity: summarize_case_activity.
Invokes the AI Summary Service (/summarize) to produce clinical summary,
risk factors breakdown, and deterministic peer comparison narrative.
"""

from typing import Any, Dict, Optional
import httpx
from temporalio import activity

from src.config import settings
from activities.params import SummarizeResult, get_system_auth_headers


@activity.defn(name="summarize_case_activity")
async def summarize_case_activity(
    case_id: str,
    claim_ref: str,
    risk_score: int,
    evidence_pointers: Optional[Dict[str, Any]] = None,
) -> SummarizeResult:
    """
    Invokes the AI Summary Service (/summarize) to produce clinical summary
    and deterministic peer comparison narrative.
    """
    url = f"{settings.AI_SUMMARY_URL}/summarize"
    activity.logger.info(
        f"Calling AI Summary Service at '{url}' for case_id='{case_id}', "
        f"claim_ref='{claim_ref}', risk_score={risk_score}..."
    )

    payload = {
        "case_id": case_id,
        "claim_ref": claim_ref,
        "risk_score": risk_score,
        "evidence_pointers": evidence_pointers or {},
    }

    headers = get_system_auth_headers()

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            err_msg = f"AI Summary Service returned status {resp.status_code}: {resp.text}"
            activity.logger.error(err_msg)
            raise RuntimeError(err_msg)

        data = resp.json()
        activity.logger.info(f"AI Summary successfully returned from service for case '{case_id}'.")

        # Persist summary to PostgreSQL via Case Management Service
        cms_url = f"{settings.CASE_MANAGEMENT_URL}/cases/{case_id}/summary"
        summary_payload = {
            "claim_ref": claim_ref,
            "clinical_summary": data.get("clinical_summary", ""),
            "risk_factors_summary": data.get("risk_factors_summary", ""),
            "peer_comparison_narrative": data.get("peer_comparison_narrative", ""),
            "confidence_score": float(data.get("confidence_score", 0.94)),
            "model_version": data.get("model_version", "foundry:qwen2.5-7b-instruct-openvino-gpu"),
        }
        
        db_resp = await client.post(cms_url, json=summary_payload, headers=headers)
        if db_resp.status_code in (200, 201):
            activity.logger.info(f"AI Summary successfully persisted to database for case '{case_id}'.")
        else:
            activity.logger.warning(
                f"Failed to persist summary to CMS database (HTTP {db_resp.status_code}): {db_resp.text}"
            )

        return SummarizeResult(
            case_id=data.get("case_id", case_id),
            clinical_summary=data.get("clinical_summary", ""),
            risk_factors_summary=data.get("risk_factors_summary", ""),
            peer_comparison_narrative=data.get("peer_comparison_narrative", ""),
            confidence_score=float(data.get("confidence_score", 0.94)),
            model_version=data.get("model_version", "foundry:qwen2.5-7b-instruct-openvino-gpu"),
        )

