"""
Temporal Client integration for Case Management Service.

Starts CaseAuditWorkflow instances upon case ingestion, enforcing idempotency
and decoupled error handling.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, Union
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

from src.config import settings

logger = logging.getLogger("case-management.temporal")


def _build_workflow_input(case: Any) -> Dict[str, Any]:
    """Extracts a serializable workflow input payload from Case ORM, Pydantic model, or dict."""
    if isinstance(case, dict):
        return {
            "case_id": case.get("case_id"),
            "claim_ref": case.get("claim_ref"),
            "risk_score": case.get("risk_score", 0),
            "flagged_reason": case.get("flagged_reason", ""),
            "source_module": case.get("source_module", "fwa_detection"),
            "facility_npi": case.get("facility_npi", ""),
            "facility_name": case.get("facility_name", ""),
            "doctor_npi": case.get("doctor_npi", ""),
            "doctor_name": case.get("doctor_name", ""),
            "patient_id": case.get("patient_id"),
            "total_claim_amount": float(case.get("total_claim_amount", 0.0)),
            "evidence_pointers": case.get("evidence_pointers", {}),
            "is_synthetic": case.get("is_synthetic", True),
        }

    # Extract from SQLAlchemy Case ORM model or Pydantic CaseCreate model
    evidence_ptrs = getattr(case, "evidence_pointers", {})
    if hasattr(evidence_ptrs, "model_dump"):
        evidence_ptrs = evidence_ptrs.model_dump(mode="json")
    elif not isinstance(evidence_ptrs, dict):
        evidence_ptrs = {}

    return {
        "case_id": getattr(case, "case_id", ""),
        "claim_ref": getattr(case, "claim_ref", ""),
        "risk_score": getattr(case, "risk_score", 0),
        "flagged_reason": getattr(case, "flagged_reason", ""),
        "source_module": getattr(case, "source_module", "fwa_detection"),
        "facility_npi": getattr(case, "facility_npi", ""),
        "facility_name": getattr(case, "facility_name", ""),
        "doctor_npi": getattr(case, "doctor_npi", ""),
        "doctor_name": getattr(case, "doctor_name", ""),
        "patient_id": getattr(case, "patient_id", None),
        "total_claim_amount": float(getattr(case, "total_claim_amount", 0.0) or 0.0),
        "evidence_pointers": evidence_ptrs,
        "is_synthetic": getattr(case, "is_synthetic", True),
    }


async def start_case_workflow_async(case: Any) -> Optional[str]:
    """
    Asynchronously starts a new CaseAuditWorkflow instance in Temporal.

    :param case: Case model or dict.
    :return: Workflow Run ID if started, or None if skipped/errored.
    """
    if not settings.TEMPORAL_AUTO_TRIGGER:
        logger.info("Temporal auto-trigger is disabled in config. Skipping workflow start.")
        return None

    input_payload = _build_workflow_input(case)
    case_id = input_payload["case_id"]
    workflow_id = f"case-audit-{case_id}"

    try:
        logger.info(f"Connecting to Temporal at '{settings.temporal_address}' for case '{case_id}'...")
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.TEMPORAL_NAMESPACE,
        )

        logger.info(
            f"Starting 'CaseAuditWorkflow' with ID '{workflow_id}' on queue '{settings.TEMPORAL_TASK_QUEUE}'..."
        )

        handle = await client.start_workflow(
            "CaseAuditWorkflow",
            input_payload,
            id=workflow_id,
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info(f"Successfully triggered Temporal workflow for case '{case_id}' (Run ID: {handle.result_run_id}).")
        return handle.result_run_id

    except WorkflowAlreadyStartedError:
        logger.warning(
            f"Temporal workflow '{workflow_id}' is already running or completed. Enforcing idempotency."
        )
        return workflow_id
    except Exception as exc:
        logger.error(
            f"Failed to trigger Temporal workflow for case '{case_id}': {exc}. "
            f"Database record remains intact."
        )
        return None


def start_case_workflow(case: Any) -> Optional[str]:
    """
    Synchronous wrapper for start_case_workflow_async, suitable for synchronous consumer loops.
    """
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If called inside an existing running event loop, schedule as background task
            asyncio.create_task(start_case_workflow_async(case))
            return "SCHEDULED_ASYNC"
        else:
            return asyncio.run(start_case_workflow_async(case))
    except Exception as exc:
        logger.error(f"Error in synchronous workflow trigger: {exc}")
        return None
