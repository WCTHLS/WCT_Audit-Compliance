"""
Workflow input and output parameter definitions for Temporal CaseAuditWorkflow.

Using dataclasses for seamless JSON serialization and deserialization across
Temporal workflow execution boundaries.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class CaseWorkflowInput:
    """Input payload required to initiate a CaseAuditWorkflow instance."""
    case_id: str
    claim_ref: str
    risk_score: int
    flagged_reason: str = ""
    source_module: str = "fwa_detection"
    facility_npi: str = ""
    facility_name: str = ""
    doctor_npi: str = ""
    doctor_name: str = ""
    patient_id: Optional[str] = None
    total_claim_amount: float = 0.0
    evidence_pointers: Optional[Dict[str, Any]] = field(default_factory=dict)
    is_synthetic: bool = True


@dataclass
class CaseWorkflowResult:
    """Final result returned by CaseAuditWorkflow upon completion or resolution."""
    case_id: str
    claim_ref: str
    status: str
    decision: Optional[str] = None
    decision_rationale: Optional[str] = None
    regulatory_basis: Optional[str] = None
    sla_breached: bool = False
    completed_at: Optional[str] = None
    message: str = "Workflow executed successfully."
