"""
Integration tests for /screen and /health API endpoints and Mock Cases 001-006.
"""


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "exclusion-screening-svc"
    assert "SYNTHETIC" in data["record_counts"]


def test_screen_case_005(client):
    """
    Case 005: Dr. Leonard Hask (NPI MATCH) + Evergreen Mobility Supply LLC (POSSIBLE_MATCH).
    Overall result should be MATCH.
    """
    payload = {
        "case_id": "CASE-2026-005",
        "claim_ref": "CLM-2026-5590",
        "doctor_npi": "1245093876",
        "doctor_name": "Dr. Leonard Hask, MD",
        "facility_npi": "1386920475",
        "facility_name": "Evergreen Mobility Supply LLC",
        "evidence_pointers": {
            "clinical_evidence": "mock-data/pi-mock/case_005_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_005_risk_factors.json",
        },
    }
    response = client.post("/screen", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "CASE-2026-005"
    assert data["overall_result"] == "MATCH"
    assert data["requires_auditor_confirmation"] is True
    
    # Verify entity results
    ordering = next((r for r in data["results"] if r["role"] == "ordering_provider"), None)
    assert ordering is not None
    assert ordering["result"] == "MATCH"
    assert ordering["match_basis"] == "npi"


def test_screen_case_006(client):
    """
    Case 006: FWA-only case with Dr. Samuel Okafor (no NPI in exclusion record -> POSSIBLE_MATCH).
    Overall result should be POSSIBLE_MATCH.
    """
    payload = {
        "case_id": "CASE-2026-006",
        "claim_ref": "CLM-2026-7712",
        "doctor_name": "Dr. Samuel Okafor, PhD",
        "evidence_pointers": {
            "risk_factors": "mock-data/fwa-mock/case_006_risk_factors.json",
        },
    }
    response = client.post("/screen", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "CASE-2026-006"
    assert data["overall_result"] == "POSSIBLE_MATCH"
    assert data["requires_auditor_confirmation"] is True


def test_screen_case_001_clean(client):
    """
    Case 001: Clean provider (NO_MATCH).
    """
    payload = {
        "case_id": "CASE-2026-001",
        "claim_ref": "CLM-2026-8841",
        "doctor_npi": "1093847562",
        "doctor_name": "Dr. Sarah Jenkins, MD",
        "facility_npi": "1982736450",
        "facility_name": "Metro Cardiology Associates",
        "evidence_pointers": {
            "clinical_evidence": "mock-data/pi-mock/case_001_clinical_evidence.json",
            "risk_factors": "mock-data/fwa-mock/case_001_risk_factors.json",
        },
    }
    response = client.post("/screen", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "CASE-2026-001"
    assert data["overall_result"] == "NO_MATCH"
    assert data["requires_auditor_confirmation"] is False
