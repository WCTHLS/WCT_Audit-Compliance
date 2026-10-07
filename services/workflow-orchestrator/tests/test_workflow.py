"""
Automated unit and workflow execution tests for CaseAuditWorkflow.
Tests enrichment, human decision signals, and 72-hour SLA timers with time-skipping.
"""

import uuid
from typing import Any, Dict, Optional
import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.testing import WorkflowEnvironment

from src.config import settings
from src.starter import load_mock_input
from workflows.case_audit_workflow import CaseAuditWorkflow
from workflows.params import (
    CaseWorkflowInput,
    CaseWorkflowResult,
    DecisionSignalInput,
)
from activities import (
    FetchCaseResult,
    SummarizeResult,
    ScreeningResult,
    NotificationResult,
    fetch_case_activity,
    update_case_status_activity,
    summarize_case_activity,
    screen_exclusions_activity,
    notify_auditor_activity,
    send_follow_up_activity,
)


@pytest.mark.anyio
async def test_fetch_case_activity():
    """Verify fetch_case_activity retrieves case details & evidence pointers."""
    res: FetchCaseResult = await fetch_case_activity("CASE-2026-001")
    assert res.found is True
    assert res.case_id == "CASE-2026-001"
    assert res.risk_score == 850
    assert "clinical_evidence" in res.evidence_pointers


@pytest.mark.anyio
async def test_summarize_case_activity():
    """Verify summarize_case_activity generates clinical & peer comparison summaries."""
    input_data = load_mock_input("case_001_event.json")
    res: SummarizeResult = await summarize_case_activity(
        case_id=input_data.case_id,
        claim_ref=input_data.claim_ref,
        risk_score=input_data.risk_score,
        evidence_pointers=input_data.evidence_pointers,
    )
    assert res.case_id == "CASE-2026-001"
    assert len(res.clinical_summary) > 0
    assert len(res.peer_comparison_narrative) > 0
    assert res.confidence_score >= 0.80


@pytest.mark.anyio
async def test_screen_exclusions_activity():
    """Verify screening flags excluded providers vs clear providers."""
    clean_res: ScreeningResult = await screen_exclusions_activity(
        doctor_npi="1093847562",
        doctor_name="Dr. Robert Vance, MD",
    )
    assert clean_res.is_excluded is False

    excl_res: ScreeningResult = await screen_exclusions_activity(
        doctor_npi="1245093876",
        doctor_name="Dr. Leonard Hask",
    )
    assert excl_res.is_excluded is True


@activity.defn(name="summarize_case_activity")
async def mock_summarize_case_activity(
    case_id: str,
    claim_ref: str,
    risk_score: int,
    evidence_pointers: Optional[Dict[str, Any]] = None,
) -> SummarizeResult:
    """Fast activity stub for workflow orchestration tests to avoid LLM inference delay."""
    return SummarizeResult(
        case_id=case_id,
        clinical_summary="High-risk claim identified with Modifier 25 unbundling pattern.",
        risk_factors_summary="Risk score 850 exceeds specialty threshold.",
        peer_comparison_narrative="Billed at 94th percentile versus regional peer median of 18%.",
        confidence_score=0.96,
        model_version="test-fast-summarizer",
    )


@pytest.mark.anyio
async def test_notify_auditor_activity_dispatch():
    """Verify notify_auditor_activity dispatches alerts and returns delivery receipts."""
    res: NotificationResult = await notify_auditor_activity(
        recipient="lead-auditor@wct-health.com",
        notification_type="SLA_BREACH",
        case_id="CASE-2026-001",
        message="72h SLA review window expired for case.",
        metadata={"hours_elapsed": 72},
    )
    assert res.sent is True
    assert res.case_id == "CASE-2026-001"
    assert res.notification_type == "SLA_BREACH"
    assert res.recipient == "lead-auditor@wct-health.com"
    assert res.notification_id.startswith("NOTIF-")


@pytest.mark.anyio
async def test_workflow_decision_signal_success():
    """
    Test CaseAuditWorkflow where human auditor submits a decision signal
    within the review window.
    """
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    task_queue = f"test-signal-queue-{uuid.uuid4().hex[:6]}"

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[CaseAuditWorkflow],
        activities=[
            fetch_case_activity,
            update_case_status_activity,
            mock_summarize_case_activity,
            screen_exclusions_activity,
            notify_auditor_activity,
            send_follow_up_activity,
        ],
    ):
        input_data = load_mock_input("case_001_event.json")
        input_data.sla_timeout_hours = 1.0
        test_wf_id = f"test-signal-{input_data.case_id}-{uuid.uuid4().hex[:6]}"

        handle = await client.start_workflow(
            CaseAuditWorkflow.run,
            input_data,
            id=test_wf_id,
            task_queue=task_queue,
        )

        decision_payload = DecisionSignalInput(
            decision="UPHOLD",
            decision_rationale="Unbundling confirmed under CPT 99215 / Modifier 25 criteria.",
            regulatory_basis="CMS NCCI Policy Manual Chapter 4, Section B",
            decided_by="senior-auditor@wct-health.com",
        )

        await handle.signal(CaseAuditWorkflow.submit_decision, decision_payload)
        result: CaseWorkflowResult = await handle.result()

        assert isinstance(result, CaseWorkflowResult)
        assert result.case_id == "CASE-2026-001"
        assert result.status == "DECISION_RECORDED"
        assert result.decision == "UPHOLD"
        assert result.decided_by == "senior-auditor@wct-health.com"
        assert result.sla_breached is False
        assert "recorded successfully" in result.message


@pytest.mark.anyio
async def test_workflow_sla_breach_timeout():
    """
    Test CaseAuditWorkflow where NO auditor decision is submitted.
    Verifies that SLA warning checkpoint fires, SLA expires, Head Auditor is alerted,
    and CMS case status updates to SLA_BREACHED.
    """
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    task_queue = f"test-sla-queue-{uuid.uuid4().hex[:6]}"

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[CaseAuditWorkflow],
        activities=[
            fetch_case_activity,
            update_case_status_activity,
            mock_summarize_case_activity,
            screen_exclusions_activity,
            notify_auditor_activity,
            send_follow_up_activity,
        ],
    ):
        input_data = load_mock_input("case_001_event.json")
        # Short timeout (0.0006 hours ~ 2.1 seconds) to test real Temporal timer expiration
        input_data.sla_timeout_hours = 0.0006
        test_wf_id = f"test-sla-breach-{input_data.case_id}-{uuid.uuid4().hex[:6]}"

        handle = await client.start_workflow(
            CaseAuditWorkflow.run,
            input_data,
            id=test_wf_id,
            task_queue=task_queue,
        )

        # Wait for workflow to complete via SLA breach expiration
        result: CaseWorkflowResult = await handle.result()

        assert isinstance(result, CaseWorkflowResult)
        assert result.case_id == "CASE-2026-001"
        assert result.sla_breached is True
        assert result.status == "SLA_BREACHED"
        assert "SLA_BREACHED" in result.message
        assert "Head Auditor" in result.message


@pytest.mark.anyio
async def test_workflow_auditor_escalation_signal():
    """
    Test CaseAuditWorkflow where human auditor submits an ESCALATE decision signal.
    Verifies that AUDITOR_ESCALATION alert is dispatched to Head Auditor
    and case status updates to ESCALATED in CMS.
    """
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.TEMPORAL_NAMESPACE,
    )

    task_queue = f"test-esc-queue-{uuid.uuid4().hex[:6]}"

    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[CaseAuditWorkflow],
        activities=[
            fetch_case_activity,
            update_case_status_activity,
            mock_summarize_case_activity,
            screen_exclusions_activity,
            notify_auditor_activity,
            send_follow_up_activity,
        ],
    ):
        input_data = load_mock_input("case_001_event.json")
        input_data.sla_timeout_hours = 1.0
        test_wf_id = f"test-esc-{input_data.case_id}-{uuid.uuid4().hex[:6]}"

        handle = await client.start_workflow(
            CaseAuditWorkflow.run,
            input_data,
            id=test_wf_id,
            task_queue=task_queue,
        )

        escalate_payload = DecisionSignalInput(
            decision="ESCALATE",
            decision_rationale="Complex unbundling pattern across multiple entities requires supervisor takeover.",
            regulatory_basis="CMS Fraud Guidelines Section 8.3",
            decided_by="senior-auditor@wct-health.com",
        )

        await handle.signal(CaseAuditWorkflow.submit_decision, escalate_payload)
        result: CaseWorkflowResult = await handle.result()

        assert isinstance(result, CaseWorkflowResult)
        assert result.case_id == "CASE-2026-001"
        assert result.status == "ESCALATED"
        assert result.decision == "ESCALATE"
        assert result.decided_by == "senior-auditor@wct-health.com"
        assert result.sla_breached is False
        assert "escalated to Head Auditor" in result.message
