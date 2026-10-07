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

import asyncio
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
        update_case_status_activity,
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
        self.assigned_auditor: Optional[str] = None
        self.sla_timeout_hours: float = 72.0

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
        self.assigned_auditor = getattr(input_data, "assigned_auditor", None) or "auditor-queue@wct-health.com"
        if getattr(input_data, "sla_timeout_hours", None):
            self.sla_timeout_hours = input_data.sla_timeout_hours

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
        # Phase 2 & 3: Run AI Summary & Exclusion Screening in Parallel
        # -------------------------------------------------------------
        summary_future = workflow.execute_activity(
            summarize_case_activity,
            args=[
                self.case_id,
                self.claim_ref,
                case_details.risk_score,
                case_details.evidence_pointers,
            ],
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=standard_retry,
        )

        screen_future = workflow.execute_activity(
            screen_exclusions_activity,
            args=[
                case_details.doctor_npi or "1093847562",
                case_details.doctor_name or "Dr. Robert Vance, MD",
                case_details.facility_npi,
                self.case_id,
                self.claim_ref,
                case_details.facility_name,
                case_details.evidence_pointers,
            ],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=standard_retry,
        )

        summary_res, screen_res = await asyncio.gather(summary_future, screen_future)

        self.clinical_summary = summary_res.clinical_summary
        self.peer_comparison_narrative = summary_res.peer_comparison_narrative
        self.is_excluded = screen_res.is_excluded

        # -------------------------------------------------------------
        # Phase 4: Notify Assigned Auditor / Queue
        # -------------------------------------------------------------
        await workflow.execute_activity(
            notify_auditor_activity,
            args=[
                self.assigned_auditor or "auditor-queue@wct-health.com",
                "CASE_ASSIGNMENT",
                self.case_id,
                f"Case {self.case_id} is enriched and ready for review. 72-hour SLA active.",
                {"risk_score": case_details.risk_score, "claim_ref": self.claim_ref},
            ],
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=standard_retry,
        )

        # -------------------------------------------------------------
        # Phase 5: 72-Hour Review Window with Early SLA Warning Checkpoint
        # -------------------------------------------------------------
        self.current_status = "READY_FOR_REVIEW"
        workflow.logger.info(
            f"Case '{self.case_id}' is in READY_FOR_REVIEW. "
            f"Entering {self.sla_timeout_hours}-hour SLA timer..."
        )

        # Proportional or fixed warning window: 6 hours before expiry for production 72h SLA,
        # or 75% elapsed for short development/test timeouts.
        if self.sla_timeout_hours > 12:
            warning_hours = float(self.sla_timeout_hours - 6)
            remaining_hours = 6.0
        else:
            warning_hours = float(self.sla_timeout_hours * 0.75)
            remaining_hours = float(self.sla_timeout_hours * 0.25)

        # Checkpoint A: Wait until early warning threshold
        try:
            await workflow.wait_condition(
                lambda: self.decision is not None,
                timeout=timedelta(hours=warning_hours),
            )
        except Exception:
            pass

        # Checkpoint B: If still no decision at warning threshold, fire SLA_BREACH_WARNING
        if self.decision is None:
            workflow.logger.warning(
                f"SLA WARNING: Case '{self.case_id}' has {remaining_hours:.1f} hours remaining before deadline."
            )
            await workflow.execute_activity(
                notify_auditor_activity,
                args=[
                    self.assigned_auditor or "auditor-queue@wct-health.com",
                    "SLA_BREACH_WARNING",
                    self.case_id,
                    f"Warning: Case {self.case_id} has {remaining_hours:.1f} hours remaining before the 72-hour SLA expires.",
                    {"hours_remaining": remaining_hours, "risk_score": case_details.risk_score},
                ],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )

            # Wait remaining time until final 72h expiration
            try:
                await workflow.wait_condition(
                    lambda: self.decision is not None,
                    timeout=timedelta(hours=remaining_hours),
                )
            except Exception:
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

            # 1. Update status in Case Management Service database
            await workflow.execute_activity(
                update_case_status_activity,
                args=[self.case_id, "SLA_BREACHED"],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )

            # 2. Trigger SLA_BREACH Alert to Head Auditor
            await workflow.execute_activity(
                notify_auditor_activity,
                args=[
                    "lead-auditor@wct-health.com",
                    "SLA_BREACH",
                    self.case_id,
                    f"URGENT: 72h SLA Breached for Case {self.case_id} (Claim {self.claim_ref})! "
                    f"Risk Score: {case_details.risk_score}. Immediate supervisor intervention required.",
                    {"sla_breached": True, "risk_score": case_details.risk_score},
                ],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )
            completion_message = "72h SLA review window expired. Case marked SLA_BREACHED and alert dispatched to Head Auditor."
        elif self.decision.upper() == "ESCALATE":
            # Auditor explicitly requested supervisor escalation!
            self.current_status = "ESCALATED"
            workflow.logger.warning(
                f"AUDITOR ESCALATION! Case '{self.case_id}' escalated by '{self.decided_by}'. "
                f"Rationale: {self.decision_rationale}"
            )

            # 1. Update status in Case Management Service database
            await workflow.execute_activity(
                update_case_status_activity,
                args=[self.case_id, "ESCALATED"],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )

            # 2. Trigger AUDITOR_ESCALATION Alert to Head Auditor
            await workflow.execute_activity(
                notify_auditor_activity,
                args=[
                    "lead-auditor@wct-health.com",
                    "AUDITOR_ESCALATION",
                    self.case_id,
                    f"Auditor Escalation for Case {self.case_id} (Claim {self.claim_ref}) by {self.decided_by}: "
                    f"{self.decision_rationale or 'Case escalated for supervisor review.'}",
                    {
                        "escalated_by": self.decided_by,
                        "rationale": self.decision_rationale,
                        "risk_score": case_details.risk_score,
                    },
                ],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
            )
            completion_message = f"Case escalated to Head Auditor by {self.decided_by}."
        else:
            # Auditor successfully recorded decision within SLA window
            self.current_status = "DECISION_RECORDED"
            workflow.logger.info(
                f"Decision '{self.decision}' successfully recorded for case '{self.case_id}' "
                f"by '{self.decided_by}' within SLA window."
            )

            # Update status in Case Management Service database
            await workflow.execute_activity(
                update_case_status_activity,
                args=[self.case_id, "DECISION_RECORDED"],
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=standard_retry,
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
