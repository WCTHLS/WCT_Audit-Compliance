"""
Temporal Workflow definition for WCT Module 5 Case Audit.

Coordinates the full lifecycle of an audit case:
1. Fetches case details & evidence pointers (fetch_case_activity)
2. Generates clinical summary & peer comparison (summarize_case_activity)
3. Screens physician against federal exclusions (screen_exclusions_activity)
4. Notifies assigned auditor (notify_auditor_activity)
5. Enforces 72-hour human-in-the-loop SLA review window
6. Triggers escalation alert if SLA expires without a decision
"""

from datetime import timedelta
from typing import Any, Dict, Optional
from temporalio import workflow
from temporalio.common import RetryPolicy

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
    from workflows.params import (
        CaseWorkflowInput,
        CaseWorkflowResult,
        DecisionSignalInput,
    )


@workflow.defn(name="CaseAuditWorkflow")
class CaseAuditWorkflow:
    """
    Durable workflow coordinating the audit lifecycle for a single case.
    Executes enrichment activities, pauses for human auditor review with a
    72-hour SLA timer, and triggers escalation on SLA breach.
    """

    def __init__(self) -> None:
        self.case_id: str = ""
        self.claim_ref: str = ""
        self.current_status: str = "INITIALIZED"
        self.decision: Optional[str] = None
        self.decision_rationale: Optional[str] = None
        self.regulatory_basis: Optional[str] = None
        self.decided_by: Optional[str] = None
        self.decided_at: Optional[str] = None
        self.sla_breached: bool = False
        self.clinical_summary: Optional[str] = None
        self.peer_comparison_narrative: Optional[str] = None
        self.is_excluded: bool = False
        self.sla_timeout_hours: int = 72

    @workflow.signal(name="submit_decision")
    def submit_decision(self, decision_data: DecisionSignalInput) -> None:
        """
        Signal handler allowing human auditors to submit case decisions in real time.
        """
        workflow.logger.info(
            f"Received auditor decision signal for case_id='{self.case_id}': "
            f"decision='{decision_data.decision}', decided_by='{decision_data.decided_by}'"
        )
        self.decision = decision_data.decision
        self.decision_rationale = decision_data.decision_rationale
        self.regulatory_basis = decision_data.regulatory_basis
        self.decided_by = decision_data.decided_by
        self.decided_at = decision_data.decided_at or workflow.now().isoformat()

    @workflow.query(name="get_case_status")
    def get_case_status(self) -> Dict[str, Any]:
        """
        Query handler to inspect live workflow state without side effects.
        """
        return {
            "case_id": self.case_id,
            "claim_ref": self.claim_ref,
            "status": self.current_status,
            "decision": self.decision,
            "sla_breached": self.sla_breached,
            "is_excluded": self.is_excluded,
        }

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
        # Phase 1: Fetch full case details from Case Management Service
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
        # Phase 2: Generate AI Summary & Deterministic Peer Comparison
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

        # -------------------------------------------------------------
        # Phase 3: Screen Physician against OIG LEIE Exclusions
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

        # -------------------------------------------------------------
        # Phase 4: Notify Assigned Auditor
        # -------------------------------------------------------------
        await workflow.execute_activity(
            notify_auditor_activity,
            args=[
                "auditor-queue@wct-health.com",
                "CASE_READY_FOR_REVIEW",
                self.case_id,
                f"Case {self.case_id} is enriched and ready for review. 72-hour SLA active.",
            ],
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=standard_retry,
        )

        # -------------------------------------------------------------
        # Phase 5: 72-Hour Human-in-the-Loop Review Window (SLA Timer)
        # -------------------------------------------------------------
        self.current_status = "READY_FOR_REVIEW"
        workflow.logger.info(
            f"Case '{self.case_id}' is in READY_FOR_REVIEW. "
            f"Entering {self.sla_timeout_hours}-hour SLA timer..."
        )

        # Wait until auditor submits a decision signal OR 72h timer expires
        try:
            await workflow.wait_condition(
                lambda: self.decision is not None,
                timeout=timedelta(hours=self.sla_timeout_hours),
            )
        except Exception:
            # Catch timeout or interruption
            pass

        # -------------------------------------------------------------
        # Phase 6: Evaluate Decision vs SLA Breach
        # -------------------------------------------------------------
        if self.decision is None:
            # 72 Hours Expired with NO Auditor Action -> SLA Breach!
            self.sla_breached = True
            self.current_status = "SLA_BREACHED"
            workflow.logger.warning(
                f"SLA BREACH! 72-hour review window expired for case '{self.case_id}'. Escalating..."
            )

            # Trigger Escalation Alert Activity
            await workflow.execute_activity(
                notify_auditor_activity,
                args=[
                    "lead-compliance-officer@wct-health.com",
                    "SLA_BREACH_ESCALATION",
                    self.case_id,
                    f"URGENT ESCALATION: 72h SLA breached for Case {self.case_id} (Claim {self.claim_ref})! "
                    f"Risk Score: {case_details.risk_score}.",
                ],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )
            completion_message = "72h SLA review window expired. Escalation alert dispatched."
        else:
            # Auditor successfully recorded decision within SLA window
            self.current_status = "DECISION_RECORDED"
            workflow.logger.info(
                f"Decision '{self.decision}' successfully recorded for case '{self.case_id}' "
                f"by '{self.decided_by}' within SLA window."
            )
            completion_message = f"Decision '{self.decision}' recorded successfully."

        return CaseWorkflowResult(
            case_id=self.case_id,
            claim_ref=self.claim_ref,
            status=self.current_status,
            decision=self.decision,
            decision_rationale=self.decision_rationale,
            regulatory_basis=self.regulatory_basis,
            decided_by=self.decided_by,
            decided_at=self.decided_at,
            sla_breached=self.sla_breached,
            completed_at=workflow.now().isoformat(),
            message=completion_message,
        )
