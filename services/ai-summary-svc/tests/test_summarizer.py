"""
Unit and integration tests for AI Summary Service.
Validates deterministic peer/risk helpers, flat case building,
number fact checking, and FastAPI narrative endpoint execution.
"""

import sys
from pathlib import Path

# Add project paths
_current_dir = Path(__file__).resolve().parent
_service_dir = _current_dir.parent
_workspace_root = _service_dir.parent.parent

for p in [
    _workspace_root / "libs" / "event-contracts",
    _workspace_root / "libs" / "evidence-lookup",
    _workspace_root / "libs" / "auth-middleware",
    _service_dir,
]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest
from fastapi.testclient import TestClient

from app.peer_comparison import compute_peer_metrics
from app.risk_factors import format_risk_factors_summary
from app.case_narrative import (
    flatten,
    build_case_text,
    build_prompt,
    check_numbers,
)
from src.main import app
from event_contracts import PeerComparisonData


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Peer Comparison Deterministic Tests
# ---------------------------------------------------------------------------

def test_peer_comparison_metrics_calculation():
    """Tests exact statistical calculations for peer comparison."""
    peer_data = PeerComparisonData(
        specialty="Interventional Cardiology",
        region="US-Northeast",
        cohort_size=184,
        provider_metric_value=88.0,
        peer_median=18.0,
        peer_percentile=98.2,
    )

    res = compute_peer_metrics(peer_data)
    assert res.specialty == "Interventional Cardiology"
    assert res.ratio_to_median == 4.89
    assert "88.0%" in res.narrative
    assert "18.0%" in res.narrative


# ---------------------------------------------------------------------------
# 2. Risk Factors & SHAP Explainability Tests
# ---------------------------------------------------------------------------

def test_risk_factors_summary_ranking():
    """Tests that risk factors are ranked by SHAP value descending."""
    mock_risk = {
        "model_metadata": {
            "model_name": "WCT-FWA-XGBoost-Ensemble-v3",
            "risk_score": 850,
            "confidence_level": 0.94,
        },
        "risk_factors": [
            {
                "factor_name": "CLAIM_VELOCITY_ANOMALY",
                "feature_value": 34.0,
                "benchmark_median": 12.0,
                "shap_value": 0.09,
                "description": "High daily volume",
            },
            {
                "factor_name": "MODIFIER_25_UTILIZATION_RATE",
                "feature_value": 0.88,
                "benchmark_median": 0.18,
                "shap_value": 0.42,
                "description": "Frequent Mod 25",
            },
        ],
    }

    res = format_risk_factors_summary(mock_risk)
    assert res.risk_score == 850
    assert res.top_factor_name == "MODIFIER_25_UTILIZATION_RATE"
    assert res.top_shap_value == 0.42


# ---------------------------------------------------------------------------
# 3. Case Flattening & Number Fact-Checking Tests
# ---------------------------------------------------------------------------

def test_build_case_text_and_fact_checker():
    """Tests case flattening and number consistency guard."""
    case_mock = {
        "event": {"case_id": "CASE-2026-001", "claim_ref": "CLM-2026-8841", "risk_score": 850},
        "clinical": {
            "patient_demographics": {"age": 62, "gender": "M", "insurance_type": "Medicare Advantage"},
            "rendering_provider": {"name": "Dr. Robert Vance", "specialty": "Interventional Cardiology"},
            "facility": {"name": "Memorial Health System", "pos_code": "11"},
            "diagnoses": [{"code": "I25.10", "description": "CAD", "is_primary": True}],
            "claim_lines": [
                {"line_number": 1, "cpt_code": "99215", "modifier": "25", "billed_amount": 420.0, "allowed_amount": 280.0, "diagnosis_pointer": ["I25.10"]},
                {"line_number": 2, "cpt_code": "93000", "modifier": None, "billed_amount": 180.0, "allowed_amount": 75.0, "diagnosis_pointer": ["I25.10"]},
                {"line_number": 3, "cpt_code": "93306", "modifier": None, "billed_amount": 2650.0, "allowed_amount": 950.0, "diagnosis_pointer": ["I25.10"]},
            ],
            "medical_record_excerpt": "Annual cardiac follow-up. ECG performed: normal sinus rhythm.",
        },
        "risk": {"risk_factors": []},
        "peer": {"statistics": {}},
        "flags": {"flags": []},
    }

    text = build_case_text(case_mock)
    assert "CLINICAL EVIDENCE" in text
    assert "99215" in text
    assert "total billed: 3250.0" in text
    assert "total allowed: 1305.0" in text

    # Valid summary with numbers matching source
    clean_prose = (
        "Patient seen on claim CLM-2026-8841. Billed CPT 99215 ($420.00, allowed $280.00) "
        "and 93000 ($180.00, allowed $75.00). Total billed is $3,250.00 and allowed is $1,305.00."
    )
    warnings = check_numbers(clean_prose, case_mock)
    assert len(warnings) == 0

    # Hallucinated summary with ungrounded CPT, ICD-10, and unallowed dollar amount
    hallucinated_prose = (
        "Patient seen for COPD (J44.9) and emergency visit 99285 for $450.00. Contested total is $355.00."
    )
    warnings_bad = check_numbers(hallucinated_prose, case_mock)
    assert any("99285" in w for w in warnings_bad)
    assert any("J44.9" in w for w in warnings_bad)
    assert any("355.00" in w for w in warnings_bad)
    assert any("450.00" in w for w in warnings_bad)


# ---------------------------------------------------------------------------
# 4. Multi-Case Evidence Ingestion & Summarizer Tests
# ---------------------------------------------------------------------------

def test_health_endpoint(client):
    """Tests GET /health returns 200."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_summarize_endpoint_case_001_fits(client):
    """TEST 1 - Case 001 fits in token budget and executes successfully with mocked LLM."""
    from unittest.mock import AsyncMock, patch

    payload = {
        "case_id": "CASE-2026-001",
        "claim_ref": "CLM-2026-8841",
        "risk_score": 850,
        "flagged_reason": "High-confidence anomaly: Frequent unbundling of CPT 99215 with modifier 25 alongside minor diagnostic procedures.",
        "evidence_pointers": {
            "clinical_evidence": "mock-data/pi-mock/case_001_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_001_risk_factors.json",
            "peer_comparison": {
                "specialty": "Interventional Cardiology",
                "region": "US-Northeast",
                "cohort_size": 184,
                "provider_metric_value": 88.0,
                "peer_median": 18.0,
                "peer_percentile": 98.2,
                "fixture_ref": "mock-data/fwa-mock/case_001_peer_comparison.json",
            },
            "claim_flags": "mock-data/pi-mock/case_001_claim_flags.json",
        },
    }

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "Patient seen for CAD evaluation. Billed 99215-25 with 93000 and 93306."
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["case_id"] == "CASE-2026-001"
        assert data["claim_ref"] == "CLM-2026-8841"
        assert data["validation_result"] == "PASSED"
        assert data["releasable"] is True
        assert len(data["clinical_summary"]) > 0


def test_summarize_endpoint_input_too_large_guard(client):
    """TEST 1b - Extremely large input triggers INPUT_TOO_LARGE guard without invoking LLM."""
    from unittest.mock import AsyncMock, patch

    payload = {
        "case_id": "CASE-OVERSIZED",
        "claim_ref": "CLM-OVERSIZED-9999",
        "risk_score": 900,
        "evidence_pointers": {
            "claim_flags": "mock-data/pi-mock/case_001_claim_flags.json",
        },
    }

    oversized_case = {
        "event": {"case_id": "CASE-OVERSIZED", "claim_ref": "CLM-OVERSIZED-9999", "risk_score": 900},
        "flags": {"flags": [{"flag_type": "ANOMALY", "description": "excessive token length test word " * 40000}]},
    }

    with patch("app.summarizer.CaseSummarizer._load_case", return_value=oversized_case), \
         patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["validation_result"] == "INPUT_TOO_LARGE"
        assert data["releasable"] is False
        assert any("exceeds model context limit" in w for w in data["validation_warnings"])
        mock_complete.assert_not_called()


def test_summarize_endpoint_case_002_fits(client):
    """TEST 1b - Case 002 fits in budget and executes successfully with mocked LLM."""
    from unittest.mock import AsyncMock, patch

    payload = {
        "case_id": "CASE-2026-002",
        "claim_ref": "CLM-DRG-469-1029",
        "risk_score": 920,
        "flagged_reason": "MS-DRG 469 billed instead of DRG 470.",
        "evidence_pointers": {
            "clinical_evidence": "mock-data/pi-mock/case_002_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_002_risk_factors.json",
            "peer_comparison": {
                "specialty": "Orthopedic Surgery",
                "region": "US-Midwest",
                "cohort_size": 142,
                "provider_metric_value": 38.5,
                "peer_median": 9.2,
                "peer_percentile": 99.1,
                "fixture_ref": "mock-data/fwa-mock/case_002_peer_comparison.json",
            },
            "claim_flags": "mock-data/pi-mock/case_002_claim_flags.json",
            "drg_validation": "mock-data/pi-mock/case_002_drg_validation.json",
        },
    }

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "Patient underwent elective inpatient total knee arthroplasty under DRG 469."
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["case_id"] == "CASE-2026-002"
        assert len(data["clinical_summary"]) > 20
        assert data["validation_result"] == "PASSED"
        assert data["releasable"] is True



def test_optional_drg_validation_loading():
    """TEST 2 - Optional DRG validation loading: _load_case and build_case_text include DRG evidence."""
    from app.summarizer import CaseSummarizer, SummarizeRequest

    summarizer = CaseSummarizer()
    request = SummarizeRequest(
        case_id="CASE-2026-002",
        claim_ref="CLM-DRG-469-1029",
        risk_score=920,
        flagged_reason="MS-DRG 469 billed instead of DRG 470.",
        evidence_pointers={
            "clinical_evidence": "mock-data/pi-mock/case_002_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_002_risk_factors.json",
            "peer_comparison": {
                "specialty": "Orthopedic Surgery",
                "region": "US-Midwest",
                "cohort_size": 142,
                "provider_metric_value": 38.5,
                "peer_median": 9.2,
                "peer_percentile": 99.1,
                "fixture_ref": "mock-data/fwa-mock/case_002_peer_comparison.json",
            },
            "claim_flags": "mock-data/pi-mock/case_002_claim_flags.json",
            "drg_validation": "mock-data/pi-mock/case_002_drg_validation.json",
        },
    )

    case = summarizer._load_case(request)
    assert "drg_validation" in case
    assert case["drg_validation"]["case_id"] == "CASE-2026-002"
    assert case["drg_validation"]["drg_comparison"]["billed_drg"]["drg_code"] == "469"
    assert case["drg_validation"]["drg_comparison"]["validated_drg"]["drg_code"] == "470"

    case_text = build_case_text(case)
    assert "--- DRG VALIDATION ---" in case_text
    assert "overpayment variance: 14500.0" in case_text


def test_grounded_drg_values_pass_numeric_validation():
    """TEST 3 - Grounded DRG values pass numeric validation with 0 warnings."""
    case_with_drg = {
        "event": {"case_id": "CASE-2026-002", "claim_ref": "CLM-DRG-469-1029", "risk_score": 920},
        "clinical": {
            "patient_demographics": {"patient_id": "PAT-78192"},
            "diagnoses": [{"code": "M17.11", "description": "Osteoarthritis"}],
            "medical_record_excerpt": "Right knee arthroplasty performed.",
        },
        "drg_validation": {
            "drg_comparison": {
                "billed_drg": {"drg_code": "469", "reimbursement_amount": 28500.00},
                "validated_drg": {"drg_code": "470", "reimbursement_amount": 14000.00},
                "overpayment_variance": 14500.00,
            },
            "mcc_adjudication": {
                "disputed_code": "I16.0",
                "reassigned_code": "I10",
            },
        },
    }

    grounded_summary = (
        "Claim CLM-DRG-469-1029 was billed under DRG 469 for $28,500.00. "
        "Audit validation recommends reassigning to DRG 470 ($14,000.00), "
        "yielding an overpayment variance of $14,500.00 due to unsupported secondary MCC I16.0."
    )
    warnings = check_numbers(grounded_summary, case_with_drg)
    assert warnings == []


def test_invented_value_fails_validation():
    """TEST 4 - Invented code or dollar amount fails validation and sets releasable=False."""
    case = {
        "event": {"case_id": "CASE-2026-001", "claim_ref": "CLM-2026-8841"},
        "clinical": {
            "claim_lines": [{"cpt_code": "99215", "billed_amount": 420.00, "allowed_amount": 280.00}],
            "medical_record_excerpt": "Follow up visit.",
        },
    }

    hallucinated_summary = "Patient billed CPT 99999 for $7,500.00 under DRG 999."
    warnings = check_numbers(hallucinated_summary, case)
    assert len(warnings) > 0
    assert any("99999" in w for w in warnings)
    assert any("7,500.00" in w for w in warnings)
    assert any("999" in w for w in warnings)


@pytest.mark.anyio
async def test_fwa_case_without_clinical_evidence():
    """TEST 5 - FWA case without clinical evidence attempts summarization rather than returning NO DATA."""
    from unittest.mock import AsyncMock, patch
    from app.summarizer import CaseSummarizer, SummarizeRequest

    summarizer = CaseSummarizer()
    request = SummarizeRequest(
        case_id="CASE-2026-FWA-ONLY",
        claim_ref="CLM-FWA-001",
        risk_score=910,
        flagged_reason="High risk provider billing velocity anomaly.",
        evidence_pointers={
            "risk_factors": "mock-data/fwa-mock/case_001_risk_factors.json",
            "claim_flags": "mock-data/pi-mock/case_001_claim_flags.json",
        },
    )

    case = summarizer._load_case(request)
    assert "clinical" not in case
    assert summarizer._has_meaningful_evidence(case) is True

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = "Risk factors indicate velocity anomaly with score 850."
        response = await summarizer.summarize_case(request)

        assert response.validation_result != "NO DATA"
        assert "Risk factors" in response.clinical_summary
        mock_complete.assert_called_once()


@pytest.mark.anyio
async def test_completely_empty_evidence_case():
    """TEST 6 - Completely empty evidence case returns NO DATA and does not call LLM."""
    from unittest.mock import AsyncMock, patch
    from app.summarizer import CaseSummarizer, SummarizeRequest

    summarizer = CaseSummarizer()
    request = SummarizeRequest(
        case_id="CASE-EMPTY",
        claim_ref="CLM-EMPTY-001",
        risk_score=500,
        evidence_pointers={},
    )

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        response = await summarizer.summarize_case(request)

        assert response.validation_result == "NO DATA"
        assert response.releasable is False
        assert response.confidence_score == 0.0
        assert "No usable evidence" in response.clinical_summary
        mock_complete.assert_not_called()


@pytest.mark.anyio
async def test_clean_grounded_summary_releasable():
    """TEST 7 - Clean grounded summary has 0 warnings, PASSED result, and releasable=True."""
    from unittest.mock import AsyncMock, patch
    from app.summarizer import CaseSummarizer, SummarizeRequest

    summarizer = CaseSummarizer()
    request = SummarizeRequest(
        case_id="CASE-2026-001",
        claim_ref="CLM-2026-8841",
        risk_score=850,
        evidence_pointers={
            "clinical_evidence": "mock-data/pi-mock/case_001_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_001_risk_factors.json",
        },
    )

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        # Provide narrative containing only valid codes and numbers from case 001
        mock_complete.return_value = (
            "Case CASE-2026-001 claim CLM-2026-8841 for patient PAT-44910. "
            "Billed CPT 99215 ($420.00, allowed $280.00), CPT 93000 ($180.00, allowed $75.00), "
            "and CPT 93306 ($2650.00, allowed $950.00). Diagnoses include I25.10, I10, E78.5. "
            "Risk score is 850 with confidence level 0.94."
        )
        response = await summarizer.summarize_case(request)

        assert response.validation_warnings == []
        assert response.validation_result == "PASSED"
        assert response.releasable is True


# ---------------------------------------------------------------------------
# 5. Multi-Case Fixture Ingestion, Field Survival & HCPCS Tests (Cases 001-006)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_num", ["001", "002", "003", "004", "005", "006"])
@pytest.mark.anyio
async def test_all_mock_data_cases_load_and_summarize(case_num):
    """Verifies all 6 case fixtures load correctly and produce valid summarization attempts."""
    import json
    from unittest.mock import AsyncMock, patch
    from app.summarizer import CaseSummarizer, SummarizeRequest

    fixture_path = _workspace_root / "mock-data" / "fwa-mock" / f"case_{case_num}_event.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        event_data = json.load(f)

    summarizer = CaseSummarizer()
    request = SummarizeRequest(
        case_id=event_data["case_id"],
        claim_ref=event_data["claim_ref"],
        risk_score=event_data.get("risk_score", 850),
        flagged_reason=event_data.get("flagged_reason"),
        evidence_pointers=event_data.get("evidence_pointers", {}),
    )

    case = summarizer._load_case(request)
    assert summarizer._has_meaningful_evidence(case) is True

    case_text = build_case_text(case)
    assert len(case_text.strip()) > 0

    with patch("app.summarizer.llm_client.complete", new_callable=AsyncMock) as mock_complete:
        mock_complete.return_value = f"Summary for {event_data['case_id']} with claim {event_data['claim_ref']}."
        response = await summarizer.summarize_case(request)
        assert response.validation_result != "NO DATA"
        assert response.case_id == event_data["case_id"]
        assert response.claim_ref == event_data["claim_ref"]
        if response.validation_result == "INPUT_TOO_LARGE":
            assert response.releasable is False
            assert len(response.validation_warnings) > 0
            mock_complete.assert_not_called()
        else:
            assert response.validation_result == "PASSED"
            assert response.releasable is True
            mock_complete.assert_called_once()



def test_field_survival_across_all_cases():
    """Verifies new fields across diverse case shapes survive into flattened prompt text."""
    import json
    from app.summarizer import CaseSummarizer, SummarizeRequest

    summarizer = CaseSummarizer()

    def load_case_text(num: str):
        path = _workspace_root / "mock-data" / "fwa-mock" / f"case_{num}_event.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        req = SummarizeRequest(
            case_id=data["case_id"],
            claim_ref=data["claim_ref"],
            risk_score=data.get("risk_score", 850),
            flagged_reason=data.get("flagged_reason"),
            evidence_pointers=data.get("evidence_pointers", {}),
        )
        loaded = summarizer._load_case(req)
        return loaded, build_case_text(loaded).lower()

    # Case 001: Typology and medical necessity review
    _, text1 = load_case_text("001")
    assert "typology" in text1 or "medical_necessity_review" in text1 or "medical necessity" in text1

    # Case 002: DRG validation
    _, text2 = load_case_text("002")
    assert "drg validation" in text2

    # Case 004: Negative SHAP / mitigating factor / value type
    _, text4 = load_case_text("004")
    assert "negative" in text4 or "mitigating" in text4 or "value_type" in text4 or "benchmark" in text4

    # Case 005: Fraud ring analysis and pending documents
    _, text5 = load_case_text("005")
    assert "fraud_ring_analysis" in text5 or "fraud ring" in text5 or "pending_documents" in text5 or "pending" in text5

    # Case 006: Identity fraud / conflicting record with NO clinical evidence section
    case6, text6 = load_case_text("006")
    assert "clinical" not in case6
    assert "conflicting" in text6 or "identity" in text6 or "synthetic" in text6 or "risk" in text6
    assert "--- CLINICAL EVIDENCE ---" not in text6


def test_hcpcs_level_ii_code_validation():
    """Tests HCPCS Level II code validation in check_numbers."""
    case_005 = {
        "event": {"case_id": "CASE-2026-005", "claim_ref": "CLM-2026-DME-0501"},
        "clinical": {
            "claim_lines": [
                {"line_number": 1, "cpt_code": "K0823", "billed_amount": 4200.0, "allowed_amount": 3500.0}
            ]
        }
    }
    # Valid HCPCS code present in case
    grounded_summary = "Patient billed DME wheelchair code K0823 for $4,200.00 (allowed $3,500.00)."
    warnings = check_numbers(grounded_summary, case_005)
    assert warnings == []

    # Invented HCPCS code E9999
    invented_summary = "Patient billed DME wheelchair code E9999 for $4,200.00."
    bad_warnings = check_numbers(invented_summary, case_005)
    assert any("E9999" in w for w in bad_warnings)


def test_unprefixed_arithmetic_decimal_caught_by_fact_checker():
    """Tests that ungrounded decimal amounts (like derived 943.31) are caught by check_numbers."""
    case_data = {
        "event": {"case_id": "CASE-2026-003", "claim_ref": "CLM-2026-9042"},
        "clinical": {
            "claim_lines": [
                {"line_number": 1, "cpt_code": "99214", "billed_amount": 1750.0, "allowed_amount": 806.69}
            ]
        }
    }
    # Arithmetic difference 1750.00 - 806.69 = 943.31 not in source
    summary_with_derived_math = (
        "Claim was billed for $1,750.00 with allowed $806.69. "
        "Calculated questioned amount variance of 943.31."
    )
    warnings = check_numbers(summary_with_derived_math, case_data)
    assert any("943.31" in w for w in warnings)


