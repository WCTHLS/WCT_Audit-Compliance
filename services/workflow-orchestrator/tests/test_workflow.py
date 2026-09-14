"""
Automated unit and workflow execution tests for CaseAuditWorkflow.
Tests against the live Temporal cluster (localhost:7233).
"""

import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from src.config import settings
from src.starter import load_mock_input
from workflows.case_audit_workflow import CaseAuditWorkflow
from workflows.params import CaseWorkflowInput, CaseWorkflowResult


def test_mock_input_loader():
    """Verify loading mock fixture case_001_event.json."""
    inp = load_mock_input("case_001_event.json")
    assert inp.case_id == "CASE-2026-001"
    assert inp.claim_ref == "CLM-99214-8841"
    assert inp.risk_score == 850
    assert "clinical_evidence" in inp.evidence_pointers
    assert inp.is_synthetic is True


def test_custom_workflow_input():
    """Verify creating custom workflow input dataclass."""
    inp = CaseWorkflowInput(
        case_id="CASE-TEST-999",
        claim_ref="CLM-TEST-888",
        risk_score=920,
        flagged_reason="Synthetic test reason",
    )
    assert inp.case_id == "CASE-TEST-999"
    assert inp.risk_score == 920
    assert inp.source_module == "fwa_detection"


@pytest.mark.asyncio
async def test_case_audit_workflow_execution_live():
    """
    Test CaseAuditWorkflow execution end-to-end against the local Temporal cluster.
    """
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    task_queue = "test-case-audit-queue"

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[CaseAuditWorkflow],
        activities=[],
    ):
        input_data = load_mock_input("case_001_event.json")

        import uuid
        test_wf_id = f"test-live-audit-{input_data.case_id}-{uuid.uuid4().hex[:6]}"

        result: CaseWorkflowResult = await client.execute_workflow(
            CaseAuditWorkflow.run,
            input_data,
            id=test_wf_id,
            task_queue=task_queue,
        )

        assert isinstance(result, CaseWorkflowResult)
        assert result.case_id == "CASE-2026-001"
        assert result.claim_ref == "CLM-99214-8841"
        assert result.status == "COMPLETED"
        assert result.sla_breached is False
        assert "executed successfully" in result.message
