"""
Unit tests for event contracts (CaseCreatedEvent, CaseStatusChangedEvent, EvidencePointers).
"""

from datetime import date, datetime, timezone
import json
import pytest
from pydantic import ValidationError

from event_contracts import (
    AuditDecisionEnum,
    CaseCreatedEvent,
    CaseStatusChangedEvent,
    CaseStatusEnum,
    DecisionSummary,
    EvidencePointers,
    PeerComparisonData,
    SlaTypeEnum,
)
from event_contracts.export_schemas import export_all_schemas


def test_valid_case_created_event():
    """Test creating a valid CaseCreatedEvent with complete nested structures."""
    peer_data = PeerComparisonData(
        specialty="Interventional Cardiology",
        region="US-Northeast",
        cohort_size=184,
        provider_metric_value=4.8,
        peer_median=1.2,
        peer_percentile=97.5,
        fixture_ref="mock-data/fwa-mock/case_001_peer_comparison.json",
    )

    evidence = EvidencePointers(
        clinical_evidence="mock-data/fwa-mock/case_001_clinical_evidence.json",
        risk_factors="mock-data/fwa-mock/case_001_risk_factors.json",
        peer_comparison=peer_data,
        claim_flags="mock-data/pi-mock/case_001_claim_flags.json",
    )

    event = CaseCreatedEvent(
        case_id="CASE-2026-001",
        claim_ref="CLM-99214-8841",
        facility_npi="1295847361",
        facility_name="Memorial Health System",
        doctor_npi="1093847562",
        doctor_name="Dr. Robert Vance, MD",
        patient_id="PAT-44910",
        service_date=date(2026, 8, 10),
        total_claim_amount=12500.00,
        risk_score=850,
        flagged_reason="Excessive billing of CPT 99215 with modifier 25",
        evidence_pointers=evidence,
    )

    assert event.event_type == "case.created"
    assert event.source_module == "fwa_detection"
    assert event.is_synthetic is True
    assert event.risk_score == 850
    assert event.facility_npi == "1295847361"
    assert event.doctor_npi == "1093847562"
    assert event.evidence_pointers.peer_comparison.region == "US-Northeast"

    # Test JSON serialization and deserialization round-trip
    json_str = event.model_dump_json()
    parsed_event = CaseCreatedEvent.model_validate_json(json_str)
    assert parsed_event.case_id == "CASE-2026-001"
    assert parsed_event.risk_score == 850


def test_invalid_risk_score_bounds():
    """Verify risk_score must be between 100 and 1000."""
    peer_data = PeerComparisonData(
        specialty="General Surgery",
        region="US-Midwest",
        cohort_size=50,
        provider_metric_value=2.0,
        peer_median=1.0,
    )
    evidence = EvidencePointers(
        clinical_evidence="mock-data/fwa-mock/case_002_clinical.json",
        risk_factors="mock-data/fwa-mock/case_002_risk.json",
        peer_comparison=peer_data,
    )

    # Score below 100
    with pytest.raises(ValidationError):
        CaseCreatedEvent(
            case_id="CASE-002",
            claim_ref="CLM-002",
            facility_npi="1234567890",
            facility_name="Facility A",
            doctor_npi="9876543210",
            doctor_name="Doctor B",
            total_claim_amount=500.0,
            risk_score=99,  # < 100
            flagged_reason="Test",
            evidence_pointers=evidence,
        )

    # Score above 1000
    with pytest.raises(ValidationError):
        CaseCreatedEvent(
            case_id="CASE-002",
            claim_ref="CLM-002",
            facility_npi="1234567890",
            facility_name="Facility A",
            doctor_npi="9876543210",
            doctor_name="Doctor B",
            total_claim_amount=500.0,
            risk_score=1001,  # > 1000
            flagged_reason="Test",
            evidence_pointers=evidence,
        )


def test_missing_required_identifiers():
    """Verify hospital and doctor NPI/names are strictly required."""
    peer_data = PeerComparisonData(
        specialty="Pediatrics",
        region="US-West",
        cohort_size=80,
        provider_metric_value=1.5,
        peer_median=1.0,
    )
    evidence = EvidencePointers(
        clinical_evidence="mock.json",
        risk_factors="mock.json",
        peer_comparison=peer_data,
    )

    # Missing facility_npi
    with pytest.raises(ValidationError):
        CaseCreatedEvent(
            case_id="CASE-003",
            claim_ref="CLM-003",
            facility_name="Hospital",
            doctor_npi="1234567890",
            doctor_name="Doctor",
            total_claim_amount=100.0,
            risk_score=600,
            flagged_reason="Test",
            evidence_pointers=evidence,
        )

    # Invalid NPI length (must be 10 digits)
    with pytest.raises(ValidationError):
        CaseCreatedEvent(
            case_id="CASE-003",
            claim_ref="CLM-003",
            facility_npi="123",  # Not 10 digits
            facility_name="Hospital",
            doctor_npi="1234567890",
            doctor_name="Doctor",
            total_claim_amount=100.0,
            risk_score=600,
            flagged_reason="Test",
            evidence_pointers=evidence,
        )


def test_valid_case_status_changed_event():
    """Test creating a valid CaseStatusChangedEvent with SLA and decision info."""
    event = CaseStatusChangedEvent(
        case_id="CASE-2026-001",
        claim_ref="CLM-99214-8841",
        previous_status=CaseStatusEnum.READY_FOR_REVIEW,
        new_status=CaseStatusEnum.DECISION_RECORDED,
        changed_by="auditor-01",
        changed_by_role="Auditor",
        reason="Auditor completed review and upheld denial",
        sla_type=SlaTypeEnum.INITIAL_REVIEW,
        sla_due_at=datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc),
        sla_breached=False,
        decision_summary=DecisionSummary(
            decision=AuditDecisionEnum.UPHOLD,
            rationale="Unbundled modifier 25 with no separate documentation.",
            regulatory_basis="CMS NCCI Policy Manual, Chapter 1",
        ),
    )

    assert event.event_type == "case.status.changed"
    assert event.new_status == CaseStatusEnum.DECISION_RECORDED
    assert event.decision_summary is not None
    assert event.decision_summary.decision == AuditDecisionEnum.UPHOLD


def test_appeal_flow_status_transition():
    """Test transitions into UNDER_APPEAL_REVIEW with appeal SLA timer."""
    event = CaseStatusChangedEvent(
        case_id="CASE-2026-001",
        claim_ref="CLM-99214-8841",
        previous_status=CaseStatusEnum.DISPUTED,
        new_status=CaseStatusEnum.UNDER_APPEAL_REVIEW,
        changed_by="temporal-orchestrator",
        changed_by_role="system",
        reason="Provider dispute received; appeal re-review window started",
        sla_type=SlaTypeEnum.APPEAL_REVIEW,
        sla_due_at=datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc),
        sla_breached=False,
    )

    assert event.new_status == CaseStatusEnum.UNDER_APPEAL_REVIEW
    assert event.sla_type == SlaTypeEnum.APPEAL_REVIEW


def test_schema_export(tmp_path):
    """Verify JSON Schema exporter creates valid JSON schema files."""
    export_all_schemas(tmp_path)
    created_schema_file = tmp_path / "case.created.schema.json"
    status_schema_file = tmp_path / "case.status.changed.schema.json"

    assert created_schema_file.exists()
    assert status_schema_file.exists()

    with open(created_schema_file, encoding="utf-8") as f:
        schema = json.load(f)
        assert schema["title"] == "CaseCreatedEvent"
        assert "evidence_pointers" in schema["properties"]
        assert "risk_score" in schema["properties"]
