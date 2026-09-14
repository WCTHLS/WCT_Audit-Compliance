"""
Temporal Workflow definition for WCT Module 5 Case Audit.

This workflow coordinates the full lifecycle of an audit case:
- Initial case intake and validation
- Enrichment activities (clinical summary, risk factors, peer comparison, exclusion screening)
- 72-hour SLA confirmation window / human-in-the-loop decision
- Final audit trail persistence
"""

from datetime import timedelta
from temporalio import workflow

from workflows.params import CaseWorkflowInput, CaseWorkflowResult


@workflow.defn(name="CaseAuditWorkflow")
class CaseAuditWorkflow:
    """
    Durable workflow coordinating the audit lifecycle for a single case.
    Executes in Temporal and survives server/worker restarts seamlessly.
    """

    def __init__(self) -> None:
        self.case_id: str = ""
        self.claim_ref: str = ""
        self.current_status: str = "INITIALIZED"
        self.decision: str | None = None
        self.decision_rationale: str | None = None
        self.sla_breached: bool = False

    @workflow.run
    async def run(self, input_data: CaseWorkflowInput) -> CaseWorkflowResult:
        """
        Main execution entry point for CaseAuditWorkflow.
        """
        self.case_id = input_data.case_id
        self.claim_ref = input_data.claim_ref
        self.current_status = "IN_PROGRESS"

        workflow.logger.info(
            f"Starting CaseAuditWorkflow for case_id='{self.case_id}', "
            f"claim_ref='{self.claim_ref}', risk_score={input_data.risk_score}"
        )

        # Baseline execution step:
        # (In upcoming days: activities for fetch_case, summarize, screen, notify, SLA timer)
        self.current_status = "COMPLETED"

        workflow.logger.info(
            f"CaseAuditWorkflow completed baseline execution for case_id='{self.case_id}'"
        )

        return CaseWorkflowResult(
            case_id=self.case_id,
            claim_ref=self.claim_ref,
            status=self.current_status,
            decision=self.decision,
            decision_rationale=self.decision_rationale,
            sla_breached=self.sla_breached,
            completed_at=workflow.now().isoformat(),
            message="Baseline CaseAuditWorkflow executed successfully.",
        )
