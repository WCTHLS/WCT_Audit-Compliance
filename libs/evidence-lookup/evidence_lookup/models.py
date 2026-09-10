"""
Pydantic data models for resolved evidence bundles.
Represents clinical notes, SHAP model explainability, peer distributions,
clinical edit flags, and DRG validation records.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 1. Clinical Evidence Models (EHR Notes, Demographics, Claim Lines)
# ---------------------------------------------------------------------------

class PatientDemographics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    patient_id: Optional[str] = Field(None, description="Patient identifier")
    age: Optional[int] = Field(None, ge=0, le=130, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient biological sex / gender")
    insurance_type: Optional[str] = Field(None, description="Payer product type (e.g. Medicare Advantage)")


class FacilityInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    npi: str = Field(..., description="10-digit Facility NPI")
    name: str = Field(..., description="Hospital or facility name")
    address: Optional[str] = Field(None, description="Facility address")
    pos_code: Optional[str] = Field(None, description="Place of Service code (e.g. '11' for Office)")


class RenderingProviderInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    npi: str = Field(..., description="10-digit Rendering Physician NPI")
    name: str = Field(..., description="Physician full name")
    specialty: str = Field(..., description="Physician specialty")


class DiagnosisItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str = Field(..., description="ICD-10 diagnosis code")
    description: str = Field(..., description="Diagnosis clinical description")
    is_primary: bool = Field(default=False, description="Whether this is the principal diagnosis")


class ClaimLineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    line_number: int = Field(..., ge=1, description="Claim line sequence number")
    cpt_code: str = Field(..., description="CPT / HCPCS procedure code")
    modifier: Optional[str] = Field(None, description="CPT modifier (e.g. '25')")
    description: str = Field(..., description="Procedure code description")
    units: int = Field(default=1, ge=1, description="Billed service units")
    billed_amount: Decimal = Field(..., ge=0, description="Billed dollar charge")
    allowed_amount: Optional[Decimal] = Field(None, ge=0, description="Payer allowed dollar amount")
    diagnosis_pointer: List[str] = Field(default_factory=list, description="Associated ICD-10 diagnosis codes")


class ClinicalEvidenceData(BaseModel):
    """Resolved Clinical Evidence bundle from EHR chart."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    patient_demographics: Optional[PatientDemographics] = None
    facility: Optional[FacilityInfo] = None
    rendering_provider: Optional[RenderingProviderInfo] = None
    service_date: Optional[date] = None
    diagnoses: List[DiagnosisItem] = Field(default_factory=list)
    claim_lines: List[ClaimLineItem] = Field(default_factory=list)
    medical_record_excerpt: str = Field(..., description="Raw text excerpt from physician clinical chart")
    auditor_clinical_notes: Optional[str] = Field(None, description="Expert clinical summary or edit rationale")


# ---------------------------------------------------------------------------
# 2. Risk Factors & SHAP Explainability Models
# ---------------------------------------------------------------------------

class RiskFactorItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    factor_name: str = Field(..., description="Feature code name (e.g. MODIFIER_25_UTILIZATION_RATE)")
    feature_value: float = Field(..., description="Observed metric value for the provider / claim")
    benchmark_median: float = Field(..., description="Peer median baseline benchmark")
    shap_value: float = Field(..., description="SHAP attribution score for model output")
    description: str = Field(..., description="Human-readable explanation of the anomaly")


class SHAPFeatureContribution(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., description="Feature display name")
    contribution: float = Field(..., description="Risk score points contributed by this feature")


class SHAPWaterfallData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    base_value: float = Field(..., description="Baseline risk score before feature attributions")
    final_prediction: float = Field(..., description="Final model risk score output (100-1000)")
    features: List[SHAPFeatureContribution] = Field(default_factory=list)


class RiskFactorsData(BaseModel):
    """Resolved ML Risk Factors and SHAP explainability bundle."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    model_metadata: Dict[str, Any] = Field(default_factory=dict)
    risk_factors: List[RiskFactorItem] = Field(default_factory=list)
    shap_waterfall: Optional[SHAPWaterfallData] = None


# ---------------------------------------------------------------------------
# 3. Peer Comparison & Distribution Models
# ---------------------------------------------------------------------------

class PeerStatistics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mean: Optional[float] = None
    std_dev: Optional[float] = None
    min: Optional[float] = None
    p25: Optional[float] = None
    median: float = Field(..., description="Peer cohort median value")
    p75: Optional[float] = None
    p90: Optional[float] = None
    p95: Optional[float] = None
    p99: Optional[float] = None
    max: Optional[float] = None
    computed_percentile: Optional[float] = None
    ratio_to_median: Optional[float] = None


class HistogramBucket(BaseModel):
    model_config = ConfigDict(extra="ignore")
    bucket: str = Field(..., description="Bucket range label (e.g. '0-10%')")
    provider_count: int = Field(..., ge=0, description="Count of peer providers in bucket")


class PeerComparisonDetailData(BaseModel):
    """Resolved detailed Peer Comparison distribution fixture."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    provider_npi: Optional[str] = None
    provider_name: Optional[str] = None
    specialty: str = Field(..., description="Medical specialty cohort")
    region: str = Field(..., description="Geographic region / peer market")
    metric_name: str = Field(..., description="Benchmarked clinical/billing metric")
    provider_value: float = Field(..., description="Provider's metric value")
    cohort_size: int = Field(..., ge=1, description="Number of peer providers in cohort")
    statistics: Optional[PeerStatistics] = None
    distribution_histogram: List[HistogramBucket] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 4. Clinical Edit Claim Flags & DRG Validation Models
# ---------------------------------------------------------------------------

class ClaimFlagItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    flag_code: str = Field(..., description="Flag code identifier (e.g. PI-EDIT-MOD25-UNBUNDLED)")
    severity: str = Field(default="MEDIUM", description="Violation severity level (HIGH, MEDIUM, LOW)")
    line_number: Optional[int] = Field(None, description="Affected claim line number")
    rule_name: str = Field(..., description="Rule policy title")
    regulatory_citation: Optional[str] = Field(None, description="Regulatory policy citation")
    description: str = Field(..., description="Detailed description of clinical edit flag")
    recommended_action: Optional[str] = Field(None, description="Recommended claim adjudication action")


class ClaimFlagsData(BaseModel):
    """Resolved Clinical Edit Rule Flags bundle."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    evaluated_at: Optional[str] = Field(None, description="Timestamp of evaluation")
    total_flags: Optional[int] = Field(None, description="Total count of triggered flags")
    flags: List[ClaimFlagItem] = Field(default_factory=list, description="List of triggered clinical edit flags")


class DRGDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drg_code: str = Field(..., description="MS-DRG code number")
    drg_title: str = Field(..., description="DRG clinical description")
    relative_weight: Optional[float] = None
    reimbursement_amount: Optional[Decimal] = None


class DRGComparison(BaseModel):
    model_config = ConfigDict(extra="ignore")
    billed_drg: Optional[DRGDetails] = None
    validated_drg: Optional[DRGDetails] = None
    overpayment_variance: Optional[Decimal] = None


class MCCAdjudication(BaseModel):
    model_config = ConfigDict(extra="ignore")
    disputed_code: Optional[str] = None
    disputed_title: Optional[str] = None
    clinical_finding: Optional[str] = None
    reassigned_code: Optional[str] = None
    reassigned_title: Optional[str] = None
    audit_recommendation: Optional[str] = None


class DRGValidationData(BaseModel):
    """Resolved Inpatient DRG Validation bundle."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    admission_type: Optional[str] = None
    drg_comparison: Optional[DRGComparison] = None
    mcc_adjudication: Optional[MCCAdjudication] = None


# ---------------------------------------------------------------------------
# 5. Full Aggregate Evidence Bundle
# ---------------------------------------------------------------------------

class FullEvidenceBundle(BaseModel):
    """Aggregated bundle of all resolved evidence artifacts for a case."""
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(..., description="Case identifier")
    claim_ref: str = Field(..., description="Claim reference ID")
    clinical_evidence: Optional[ClinicalEvidenceData] = None
    risk_factors: Optional[RiskFactorsData] = None
    peer_comparison_detail: Optional[PeerComparisonDetailData] = None
    claim_flags: Optional[ClaimFlagsData] = None
    drg_validation: Optional[DRGValidationData] = None
