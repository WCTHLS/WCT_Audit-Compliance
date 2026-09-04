"""
Validation tests for mock-data fixtures.
Verifies that:
1. All event JSON fixtures strictly conform to CaseCreatedEvent from libs/event-contracts.
2. Every file path in evidence_pointers actually exists and contains valid JSON.
3. Clinical evidence, risk factors, peer comparison, and claim flags fixtures have valid internal structures.
"""

import json
from pathlib import Path
import pytest
from event_contracts import CaseCreatedEvent


WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
MOCK_DATA_DIR = WORKSPACE_ROOT / "mock-data"


def test_mock_data_directory_exists():
    """Verify mock-data folder and subdirectories exist."""
    assert MOCK_DATA_DIR.exists(), f"Directory not found: {MOCK_DATA_DIR}"
    assert (MOCK_DATA_DIR / "fwa-mock").exists()
    assert (MOCK_DATA_DIR / "pi-mock").exists()


@pytest.mark.parametrize("case_num", ["case_001", "case_002"])
def test_case_event_fixture_conforms_to_schema(case_num):
    """Verify event fixture parses into CaseCreatedEvent Pydantic model without error."""
    event_file = MOCK_DATA_DIR / "fwa-mock" / f"{case_num}_event.json"
    assert event_file.exists(), f"Event fixture not found: {event_file}"

    with open(event_file, encoding="utf-8") as f:
        data = json.load(f)

    event = CaseCreatedEvent.model_validate(data)
    assert event.event_type == "case.created"
    assert event.source_module == "fwa_detection"
    assert event.is_synthetic is True
    assert 100 <= event.risk_score <= 1000
    assert len(event.facility_npi) == 10
    assert len(event.doctor_npi) == 10


@pytest.mark.parametrize("case_num", ["case_001", "case_002"])
def test_evidence_pointers_files_exist_and_are_valid_json(case_num):
    """Verify every file referenced in evidence_pointers exists and is valid JSON."""
    event_file = MOCK_DATA_DIR / "fwa-mock" / f"{case_num}_event.json"
    with open(event_file, encoding="utf-8") as f:
        data = json.load(f)

    event = CaseCreatedEvent.model_validate(data)
    pointers = event.evidence_pointers

    # 1. Clinical Evidence
    clin_file = WORKSPACE_ROOT / pointers.clinical_evidence
    assert clin_file.exists(), f"Clinical evidence file missing: {clin_file}"
    with open(clin_file, encoding="utf-8") as f:
        clin_data = json.load(f)
        assert clin_data["case_id"] == event.case_id

    # 2. Risk Factors
    risk_file = WORKSPACE_ROOT / pointers.risk_factors
    assert risk_file.exists(), f"Risk factors file missing: {risk_file}"
    with open(risk_file, encoding="utf-8") as f:
        risk_data = json.load(f)
        assert risk_data["case_id"] == event.case_id
        assert len(risk_data["risk_factors"]) >= 1

    # 3. Peer Comparison Fixture Ref (if present)
    if pointers.peer_comparison.fixture_ref:
        peer_file = WORKSPACE_ROOT / pointers.peer_comparison.fixture_ref
        assert peer_file.exists(), f"Peer comparison file missing: {peer_file}"
        with open(peer_file, encoding="utf-8") as f:
            peer_data = json.load(f)
            assert peer_data["case_id"] == event.case_id
            assert "statistics" in peer_data

    # 4. Claim Flags (if present)
    if pointers.claim_flags:
        flags_file = WORKSPACE_ROOT / pointers.claim_flags
        assert flags_file.exists(), f"Claim flags file missing: {flags_file}"
        with open(flags_file, encoding="utf-8") as f:
            flags_data = json.load(f)
            assert flags_data["case_id"] == event.case_id
            assert "flags" in flags_data


def test_case_002_drg_validation_fixture():
    """Verify Case 2 DRG validation analysis fixture exists and contains valid metrics."""
    drg_file = MOCK_DATA_DIR / "pi-mock" / "case_002_drg_validation.json"
    assert drg_file.exists()
    with open(drg_file, encoding="utf-8") as f:
        data = json.load(f)
        assert data["case_id"] == "CASE-2026-002"
        assert data["drg_comparison"]["overpayment_variance"] == 14500.00
