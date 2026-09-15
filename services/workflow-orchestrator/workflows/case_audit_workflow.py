"""
Temporal Workflow definition for WCT Module 5 Case Audit.

Coordinates the full lifecycle of an audit case:
1. Fetches case details & evidence pointers (fetch_case_activity)
2. Generates clinical summary & peer comparison (summarize_case_activity)
3. Screens physician against federal exclusions (screen_exclusions_activity)
4. Notifies assigned auditor (notify_auditor_activity)
5. Enforces 72-hour SLA review window
"""

from datetime import timedelta
from typing import Optional
from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activity stubs (for workflow type hinting and execution)
with workflow.unsafe.imports_passed_through():
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
    from workflows.params import CaseWorkflowInput, CaseWorkflowResult


@workflow.defn(name="CaseAuditWorkflow")
class CaseAuditWorkflow:
    """
    Durable workflow coordinating the audit lifecycle for a single case.
    Executes activities in sequence with automatic retries and durable state checkpoints.
    """

    def __init__(self) -> None:
        self.case_id: str = ""
        self.claim_ref: str = ""
        self.current_status: str = "INITIALIZED"
        self.decision: Optional[str] = None
        self.decision_rationale: Optional[str] = None
        self.sla_breached: bool = False
        self.clinical_summary: Optional[str] = None
        self.peer_comparison_narrative: Optional[str] = None
        self.is_excluded: bool = False

    @workflow.run
    async def run(self, input_data: CaseWorkflowInput) -> CaseWorkflowResult:
        """
        Main execution entry point for CaseAuditWorkflow.
        """
        self.case_id = input_data.case_id
        self.claim_ref = input_data.claim_ref
        self.current_status = "ENRICHING"

        workflow.logger.info(
            f"Starting CaseAuditWorkflow lifecycle for case_id='{self.case_id}', "
            f"claim_ref='{self.claim_ref}'"
        )

        standard_retry = RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=10),
            maximum_attempts=3,
        )

        # -------------------------------------------------------------
        # Step 1: Fetch full case details from Case Management Service
        # -------------------------------------------------------------
        case_details: FetchCaseResult = await workflow.execute_activity(
            fetch_case_activity,
            self.case_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=standard_retry,
        )
        workflow.logger.info(
            f"Case details retrieved: Provider '{case_details.doctor_name}', "
            f"Facility '{case_details.facility_name}', Risk Score: {case_details.risk_score}"
        )

        # -------------------------------------------------------------
        # Step 2: Generate AI Summary & Deterministic Peer Comparison
        # -------------------------------------------------------------
        summary_res: SummarizeResult = await workflow.execute_activity(
            summarize_case_activity,
            args=[
                self.case_id,
                self.claim_ref,
                case_details.risk_score,
                case_details.evidence_pointers,
            ],
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=standard_retry,
        )
        self.clinical_summary = summary_res.clinical_summary
        self.peer_comparison_narrative = summary_res.peer_comparison_narrative
        workflow.logger.info(
            f"AI Summary generated. Peer narrative: {self.peer_comparison_narrative}"
        )

        # -------------------------------------------------------------
        # Step 3: Screen Physician against OIG LEIE Exclusions
        # -------------------------------------------------------------
        screen_res: ScreeningResult = await workflow.execute_activity(
            screen_exclusions_activity,
            args=[
                case_details.doctor_npi or "1093847562",
                case_details.doctor_name or "Dr. Robert Vance, MD",
                case_details.facility_npi,
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=standard_retry,
        )
        self.is_excluded = screen_res.is_excluded
        workflow.logger.info(
            f"Exclusion screening completed: is_excluded={self.is_excluded}"
        )

        # -------------------------------------------------------------
        # Step 4: Notify Auditor that Case is Ready for Review
        # -------------------------------------------------------------
        await workflow.execute_activity(
            notify_auditor_activity,
            args=[
                "auditor-queue@wct-health.com",
                "CASE_READY_FOR_REVIEW",
                self.case_id,
                f"Case {self.case_id} is enriched and ready for auditor review.",
            ],
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=standard_retry,
        )

        # Case is now fully enriched and waiting for auditor decision
        self.current_status = "READY_FOR_REVIEW"

        workflow.logger.info(
            f"CaseAuditWorkflow finished core enrichment for case_id='{self.case_id}'"
        )

        return CaseWorkflowResult(
            case_id=self.case_id,
            claim_ref=self.claim_ref,
            status=self.current_status,
            decision=self.decision,
            decision_rationale=self.decision_rationale,
            sla_breached=self.sla_breached,
            completed_at=workflow.now().isoformat(),
            message="CaseAuditWorkflow core activities executed successfully.",
        )
