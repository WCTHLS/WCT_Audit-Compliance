"""
Unit and integration tests for EvidenceLookupClient.
Tests resolving clinical evidence, SHAP risk factors, peer comparison distributions,
clinical edit claim flags, DRG validation fixtures, and error handling.
"""

import json
from decimal import Decimal
from pathlib import Path
import pytest

from evidence_lookup import (
    EvidenceLookupClient,
    EvidenceNotFoundError,
    EvidenceParseError,
    ClinicalEvidenceData,
    RiskFactorsData,
    PeerComparisonDetailData,
    ClaimFlagsData,
    DRGValidationData,
    FullEvidenceBundle,
)

# Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


@pytest.fixture
def lookup_client():
    """Provides an instance of EvidenceLookupClient."""
    return EvidenceLookupClient(base_dir=MOCK_DATA_DIR)


@pytest.fixture
def case_001_pointers():
    """Returns evidence_pointers dictionary from case_001 fixture."""
    with open(MOCK_DATA_DIR / "fwa-mock" / "case_001_event.json", encoding="utf-8") as f:
        event = json.load(f)
    return event["evidence_pointers"]


@pytest.fixture
def case_002_pointers():
    """Returns evidence_pointers dictionary from case_002 fixture."""
    with open(MOCK_DATA_DIR / "fwa-mock" / "case_002_event.json", encoding="utf-8") as f:
        event = json.load(f)
    return event["evidence_pointers"]


def test_resolve_case_001_clinical_evidence(lookup_client, case_001_pointers):
    """Verify resolving clinical evidence extracts EHR demographics, diagnoses, and CPT claim lines."""
    clinical = lookup_client.resolve_clinical_evidence(case_001_pointers)

    assert isinstance(clinical, ClinicalEvidenceData)
    assert clinical.case_id == "CASE-2026-001"
    assert clinical.claim_ref == "CLM-99214-8841"
    assert clinical.patient_demographics.patient_id == "PAT-44910"
    assert clinical.patient_demographics.age == 62
    assert clinical.patient_demographics.insurance_type == "Medicare Advantage"
    assert clinical.facility.npi == "1295847361"
    assert clinical.rendering_provider.name == "Dr. Robert Vance, MD"

    # Diagnoses
    assert len(clinical.diagnoses) == 3
    assert clinical.diagnoses[0].code == "I25.10"
    assert clinical.diagnoses[0].is_primary is True

    # Claim Lines
    assert len(clinical.claim_lines) == 3
    cpt1 = clinical.claim_lines[0]
    assert cpt1.cpt_code == "99215"
    assert cpt1.modifier == "25"
    assert cpt1.billed_amount == Decimal("420.00")

    # Chart Excerpt
    assert "scheduled annual cardiac follow-up" in clinical.medical_record_excerpt
    assert "does not document any acute illness" in clinical.auditor_clinical_notes


def test_resolve_case_001_risk_factors_and_shap(lookup_client, case_001_pointers):
    """Verify resolving risk factors parses SHAP feature attributions and waterfall points."""
    risk = lookup_client.resolve_risk_factors(case_001_pointers)

    assert isinstance(risk, RiskFactorsData)
    assert risk.case_id == "CASE-2026-001"
    assert risk.model_metadata["model_name"] == "WCT-FWA-XGBoost-Ensemble-v3"
    assert risk.model_metadata["risk_score"] == 850

    # Risk Factors
    assert len(risk.risk_factors) == 4
    mod25_factor = next(f for f in risk.risk_factors if f.factor_name == "MODIFIER_25_UTILIZATION_RATE")
    assert mod25_factor.feature_value == 0.88
    assert mod25_factor.benchmark_median == 0.18
    assert mod25_factor.shap_value == 0.42

    # SHAP Waterfall
    assert risk.shap_waterfall is not None
    assert risk.shap_waterfall.base_value == 250
    assert risk.shap_waterfall.final_prediction == 850
    assert len(risk.shap_waterfall.features) == 4
    assert risk.shap_waterfall.features[0].name == "Mod 25 Frequency"
    assert risk.shap_waterfall.features[0].contribution == 260


def test_resolve_case_001_peer_comparison(lookup_client, case_001_pointers):
    """Verify resolving peer comparison distribution fixture and cohort statistics."""
    # Add fixture_ref pointer if not present in test dict
    pointers = dict(case_001_pointers)
    pointers["peer_comparison"]["fixture_ref"] = "fwa-mock/case_001_peer_comparison.json"

    peer = lookup_client.resolve_peer_comparison(pointers)

    assert isinstance(peer, PeerComparisonDetailData)
    assert peer.specialty == "Interventional Cardiology"
    assert peer.region == "US-Northeast"
    assert peer.cohort_size == 184
    assert peer.provider_value == 88.0

    # Statistics
    assert peer.statistics is not None
    assert peer.statistics.median == 18.0
    assert peer.statistics.computed_percentile == 98.2
    assert peer.statistics.ratio_to_median == 4.89

    # Histogram Distribution
    assert len(peer.distribution_histogram) == 9
    assert peer.distribution_histogram[0].bucket == "0-10%"
    assert peer.distribution_histogram[0].provider_count == 42


def test_resolve_case_001_claim_flags(lookup_client, case_001_pointers):
    """Verify resolving clinical edit rule flags from pi-mock."""
    pointers = dict(case_001_pointers)
    pointers["claim_flags"] = "pi-mock/case_001_claim_flags.json"

    flags = lookup_client.resolve_claim_flags(pointers)

    assert isinstance(flags, ClaimFlagsData)
    assert flags.case_id == "CASE-2026-001"
    assert flags.total_flags == 2
    assert len(flags.flags) == 2
    v = flags.flags[0]
    assert v.flag_code == "PI-EDIT-MOD25-UNBUNDLED"
    assert v.severity == "HIGH"
    assert "CMS NCCI Policy Manual" in v.regulatory_citation
    assert v.recommended_action == "DENY_LINE_ITEM"


def test_resolve_case_002_drg_validation(lookup_client, case_002_pointers):
    """Verify resolving DRG validation analysis for Case 2."""
    pointers = dict(case_002_pointers)
    pointers["drg_validation"] = "pi-mock/case_002_drg_validation.json"

    drg = lookup_client.resolve_drg_validation(pointers)

    assert isinstance(drg, DRGValidationData)
    assert drg.case_id == "CASE-2026-002"
    assert drg.admission_type == "Elective Inpatient"
    assert drg.drg_comparison is not None
    assert drg.drg_comparison.billed_drg.drg_code == "469"
    assert drg.drg_comparison.validated_drg.drg_code == "470"
    assert drg.drg_comparison.overpayment_variance == Decimal("14500.00")
    assert drg.mcc_adjudication.disputed_code == "I16.0"
    assert "transiently" in drg.mcc_adjudication.clinical_finding


def test_resolve_all_evidence_bundle(lookup_client, case_001_pointers):
    """Verify resolve_all returns a combined FullEvidenceBundle containing all sub-artifacts."""
    pointers = dict(case_001_pointers)
    pointers["peer_comparison"]["fixture_ref"] = "fwa-mock/case_001_peer_comparison.json"
    pointers["claim_flags"] = "pi-mock/case_001_claim_flags.json"

    bundle = lookup_client.resolve_all(pointers, case_id="CASE-2026-001", claim_ref="CLM-99214-8841")

    assert isinstance(bundle, FullEvidenceBundle)
    assert bundle.case_id == "CASE-2026-001"
    assert bundle.claim_ref == "CLM-99214-8841"
    assert bundle.clinical_evidence is not None
    assert bundle.risk_factors is not None
    assert bundle.peer_comparison_detail is not None
    assert bundle.claim_flags is not None


def test_error_handling_missing_and_invalid_pointers(lookup_client):
    """Verify clear exceptions are raised when evidence pointers are missing or invalid."""
    # 1. Missing clinical_evidence pointer
    with pytest.raises(EvidenceNotFoundError, match="No 'clinical_evidence' pointer"):
        lookup_client.resolve_clinical_evidence({})

    # 2. Pointer references non-existent file
    with pytest.raises(EvidenceNotFoundError, match="Evidence file could not be found"):
        lookup_client.resolve_clinical_evidence({"clinical_evidence": "fwa-mock/non_existent.json"})

    # 3. Optional resolve returns None when pointer omitted
    assert lookup_client.resolve_claim_flags({}) is None
    assert lookup_client.resolve_drg_validation({}) is None
