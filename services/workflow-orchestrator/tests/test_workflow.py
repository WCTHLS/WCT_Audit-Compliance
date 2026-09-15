"""
Automated unit and workflow execution tests for CaseAuditWorkflow and Core Activities.
"""

import uuid
import pytest
from temporalio.client import Client
from temporalio.worker import Worker

from src.config import settings
from src.starter import load_mock_input
from workflows.case_audit_workflow import CaseAuditWorkflow
from workflows.params import CaseWorkflowInput, CaseWorkflowResult
from activities import (
    FetchCaseResult,
    SummarizeResult,
    ScreeningResult,
    NotificationResult,
    fetch_case_activity,
    summarize_case_activity,
    screen_exclusions_activity,
    notify_auditor_activity,
    send_follow_up_activity,
)


@pytest.mark.asyncio
async def test_fetch_case_activity():
    """Verify fetch_case_activity retrieves case details & evidence pointers."""
    res: FetchCaseResult = await fetch_case_activity("CASE-2026-001")
    assert res.found is True
    assert res.case_id == "CASE-2026-001"
    assert res.risk_score == 850
    assert "clinical_evidence" in res.evidence_pointers


@pytest.mark.asyncio
async def test_summarize_case_activity():
    """Verify summarize_case_activity generates clinical & peer comparison summaries."""
    res: SummarizeResult = await summarize_case_activity(
        case_id="CASE-2026-001",
        claim_ref="CLM-99214-8841",
        risk_score=850,
        evidence_pointers={},
    )
    assert res.case_id == "CASE-2026-001"
    assert "Modifier 25" in res.clinical_summary
    assert "Peer Median" in res.peer_comparison_narrative
    assert res.confidence_score >= 0.90


@pytest.mark.asyncio
async def test_screen_exclusions_activity():
    """Verify screening flags excluded providers vs clear providers."""
    # Test clean provider
    clean_res: ScreeningResult = await screen_exclusions_activity(
        doctor_npi="1093847562",
        doctor_name="Dr. Robert Vance, MD",
    )
    assert clean_res.is_excluded is False

    # Test excluded provider
    excl_res: ScreeningResult = await screen_exclusions_activity(
        doctor_npi="9999999999",
        doctor_name="Dr. Excluded Clinician",
    )
    assert excl_res.is_excluded is True
    assert "1128(a)(1)" in excl_res.details


@pytest.mark.asyncio
async def test_workflow_with_activities_live():
    """
    Test CaseAuditWorkflow executing all activities in sequence against Temporal.
    """
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    task_queue = f"test-activities-queue-{uuid.uuid4().hex[:6]}"

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[CaseAuditWorkflow],
        activities=[
            fetch_case_activity,
            summarize_case_activity,
            screen_exclusions_activity,
            notify_auditor_activity,
            send_follow_up_activity,
        ],
    ):
        input_data = load_mock_input("case_001_event.json")
        test_wf_id = f"test-enrichment-{input_data.case_id}-{uuid.uuid4().hex[:6]}"

        result: CaseWorkflowResult = await client.execute_workflow(
            CaseAuditWorkflow.run,
            input_data,
            id=test_wf_id,
            task_queue=task_queue,
        )

        assert isinstance(result, CaseWorkflowResult)
        assert result.case_id == "CASE-2026-001"
        assert result.status == "READY_FOR_REVIEW"
        assert result.sla_breached is False
        assert "core activities executed successfully" in result.message
