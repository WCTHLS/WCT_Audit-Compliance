"""
Temporal Activity: summarize_case_activity.
Activity stub for AI Summary Service (generates clinical summary, risk factors, peer comparison).
"""

from typing import Any, Dict, Optional
from temporalio import activity

from activities.params import SummarizeResult


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
    activity.logger.info(
        f"Generating AI summary and peer comparison for case_id='{case_id}', "
        f"claim_ref='{claim_ref}', risk_score={risk_score}..."
    )

    # In Week 4, this calls POST /summarize on ai-summary-svc
    # For now, generates structured summary according to WCT Module 5 contracts
    clinical_summary = (
        f"Case {case_id} (Claim {claim_ref}): Routine cardiology evaluation (CPT 99215) "
        f"billed with Modifier 25 alongside ECG (93000). Documentation lacks evidence of "
        f"a significant, separately identifiable evaluation and management service."
    )

    risk_factors_summary = (
        f"Top risk contributor (SHAP +0.42): High frequency of Modifier 25 unbundling. "
        f"Overall FWA ML Risk Score: {risk_score}/1000."
    )

    peer_comparison_narrative = (
        "Provider bills CPT 99215 + Mod 25 on 88.0% of visits (Peer Median: 18.0%, "
        "98.2th Percentile in US-Northeast Interventional Cardiology cohort of 184 peers)."
    )

    activity.logger.info(f"Summary generated successfully for case '{case_id}'.")

    return SummarizeResult(
        case_id=case_id,
        clinical_summary=clinical_summary,
        risk_factors_summary=risk_factors_summary,
        peer_comparison_narrative=peer_comparison_narrative,
        confidence_score=0.96,
        model_version="gpt-4o-health-v1",
    )
