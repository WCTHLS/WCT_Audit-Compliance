"""
Pydantic schemas for Exclusion Screening API requests and responses.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ExclusionRecordDetail(BaseModel):
    """Details of a matched exclusion record."""
    source: str
    excl_type: Optional[str] = None
    excl_date: Optional[str] = None
    specialty: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    bus_name: Optional[str] = None
    npi: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class EntityScreeningResult(BaseModel):
    """Screening outcome for a single entity."""
    role: str
    name: Optional[str] = None
    npi: Optional[str] = None
    result: str  # MATCH, POSSIBLE_MATCH, NO_MATCH
    match_basis: str  # npi, individual_name, business_name, none
    record: Optional[ExclusionRecordDetail] = None


class ScreenRequest(BaseModel):
    """Request payload for POST /screen."""
    case_id: str
    claim_ref: Optional[str] = None
    doctor_npi: Optional[str] = None
    doctor_name: Optional[str] = None
    facility_npi: Optional[str] = None
    facility_name: Optional[str] = None
    evidence_pointers: Optional[Dict[str, Any]] = None


class ScreenResponse(BaseModel):
    """Response payload for POST /screen."""
    case_id: str
    overall_result: str  # MATCH, POSSIBLE_MATCH, NO_MATCH
    screened_at: str
    list_snapshot: Dict[str, str] = Field(default_factory=dict)
    results: List[EntityScreeningResult] = Field(default_factory=list)
    requires_auditor_confirmation: bool = False


class HealthResponse(BaseModel):
    """Response payload for GET /health."""
    status: str
    service: str
    record_counts: Dict[str, int]
    snapshot_info: Dict[str, str]
    timestamp: str
