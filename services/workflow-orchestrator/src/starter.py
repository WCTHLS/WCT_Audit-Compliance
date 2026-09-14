"""
Utility script to trigger a CaseAuditWorkflow execution against the Temporal cluster.
Can load sample data from mock fixtures or run with custom parameters.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from temporalio.client import Client

from src.config import settings
from workflows.case_audit_workflow import CaseAuditWorkflow
from workflows.params import CaseWorkflowInput, CaseWorkflowResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("workflow-starter")


def load_mock_input(case_filename: str = "case_001_event.json") -> CaseWorkflowInput:
    """Loads a sample case from mock fixtures or falls back to defaults."""
    # Find mock-data directory relative to repo root
    current_dir = Path(__file__).resolve().parent
    repo_root = current_dir.parent.parent.parent
    mock_file = repo_root / "mock-data" / "fwa-mock" / case_filename

    if mock_file.exists():
        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CaseWorkflowInput(
            case_id=data.get("case_id", "CASE-2026-001"),
            claim_ref=data.get("claim_ref", "CLM-99214-8841"),
            risk_score=data.get("risk_score", 850),
            flagged_reason=data.get("flagged_reason", ""),
            source_module=data.get("source_module", "fwa_detection"),
            facility_npi=data.get("facility_npi", ""),
            facility_name=data.get("facility_name", ""),
            doctor_npi=data.get("doctor_npi", ""),
            doctor_name=data.get("doctor_name", ""),
            patient_id=data.get("patient_id"),
            total_claim_amount=float(data.get("total_claim_amount", 0.0)),
            evidence_pointers=data.get("evidence_pointers", {}),
            is_synthetic=data.get("is_synthetic", True),
        )

    # Fallback default
    return CaseWorkflowInput(
        case_id="CASE-2026-001",
        claim_ref="CLM-99214-8841",
        risk_score=850,
        flagged_reason="High risk score flag",
    )


async def trigger_workflow(input_data: CaseWorkflowInput | None = None) -> CaseWorkflowResult:
    """Connects to Temporal and executes a CaseAuditWorkflow instance."""
    if input_data is None:
        input_data = load_mock_input()

    workflow_id = f"case-audit-{input_data.case_id}"

    logger.info(f"Connecting to Temporal at '{settings.temporal_address}'...")
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    logger.info(
        f"Starting workflow '{CaseAuditWorkflow.__name__}' with ID '{workflow_id}' "
        f"on queue '{settings.TASK_QUEUE}'..."
    )

    result: CaseWorkflowResult = await client.execute_workflow(
        CaseAuditWorkflow.run,
        input_data,
        id=workflow_id,
        task_queue=settings.TASK_QUEUE,
    )

    logger.info(f"Workflow execution finished successfully!")
    logger.info(f"Result -> Case ID: {result.case_id} | Status: {result.status} | Message: {result.message}")
    return result


def main() -> None:
    """CLI entry point to trigger workflow."""
    asyncio.run(trigger_workflow())


if __name__ == "__main__":
    main()
