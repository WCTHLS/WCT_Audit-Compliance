"""
WCT Evidence Lookup Library.
Provides EvidenceLookupClient and data models for resolving case evidence pointers.
"""

from evidence_lookup.client import (
    EvidenceLookupClient,
    EvidenceLookupError,
    EvidenceNotFoundError,
    EvidenceParseError,
)
from evidence_lookup.models import (
    PatientDemographics,
    FacilityInfo,
    RenderingProviderInfo,
    DiagnosisItem,
    ClaimLineItem,
    ClinicalEvidenceData,
    RiskFactorItem,
    SHAPFeatureContribution,
    SHAPWaterfallData,
    RiskFactorsData,
    PeerStatistics,
    HistogramBucket,
    PeerComparisonDetailData,
    ClaimFlagItem,
    ClaimFlagsData,
    DRGDetails,
    DRGComparison,
    MCCAdjudication,
    DRGValidationData,
    FullEvidenceBundle,
)

__all__ = [
    "EvidenceLookupClient",
    "EvidenceLookupError",
    "EvidenceNotFoundError",
    "EvidenceParseError",
    "PatientDemographics",
    "FacilityInfo",
    "RenderingProviderInfo",
    "DiagnosisItem",
    "ClaimLineItem",
    "ClinicalEvidenceData",
    "RiskFactorItem",
    "SHAPFeatureContribution",
    "SHAPWaterfallData",
    "RiskFactorsData",
    "PeerStatistics",
    "HistogramBucket",
    "PeerComparisonDetailData",
    "ClaimFlagItem",
    "ClaimFlagsData",
    "DRGDetails",
    "DRGComparison",
    "MCCAdjudication",
    "DRGValidationData",
    "FullEvidenceBundle",
]
