# WCT Mock Data Fixtures (`mock-data/`)

Standardized mock data fixtures for **Module 5: Audit & Compliance Workflow** POC.

## Overview

In the standalone POC phase, upstream modules (FWA Detection and Payment Integrity) are not connected as live services. Instead, simulated triggers and clinical context are provided via static JSON fixtures in this folder.

All audit cases reference these fixtures using the **`evidence_pointers`** convention defined in `libs/event-contracts`.

---

## Directory Structure

```text
mock-data/
├── fwa-mock/
│   ├── case_001_event.json            # CaseCreatedEvent Kafka trigger (Cardiology Mod 25)
│   ├── case_001_clinical_evidence.json# Outpatient diagnoses, CPT lines, physician chart notes
│   ├── case_001_risk_factors.json     # SHAP feature importance weights & ML anomaly scores
│   ├── case_001_peer_comparison.json  # Peer cohort distribution for peer_comparison.py
│   │
│   ├── case_002_event.json            # CaseCreatedEvent Kafka trigger (Orthopedic DRG 469)
│   ├── case_002_clinical_evidence.json# Inpatient hospital admission, operative notes, ICD-10 PCS
│   ├── case_002_risk_factors.json     # ML DRG anomaly scores & SHAP feature impacts
│   └── case_002_peer_comparison.json  # Orthopedic hospital cohort benchmarking distribution
│
└── pi-mock/
    ├── case_001_claim_flags.json      # NCCI modifier 25 unbundling edit flags
    ├── case_002_claim_flags.json      # Unsupported secondary MCC edit flags
    └── case_002_drg_validation.json   # MS-DRG 469 vs 470 payment variance analysis
```

---

## The `evidence_pointers` Resolution Convention

Each `case_created` event contains an `evidence_pointers` object:

```json
"evidence_pointers": {
  "clinical_evidence": "mock-data/fwa-mock/case_001_clinical_evidence.json",
  "risk_factors": "mock-data/fwa-mock/case_001_risk_factors.json",
  "peer_comparison": {
    "specialty": "Interventional Cardiology",
    "region": "US-Northeast",
    "cohort_size": 184,
    "provider_metric_value": 88.0,
    "peer_median": 18.0,
    "peer_percentile": 98.2,
    "fixture_ref": "mock-data/fwa-mock/case_001_peer_comparison.json"
  },
  "claim_flags": "mock-data/pi-mock/case_001_claim_flags.json"
}
```

* When the **Case Management Service** stores the case, it saves this object in the `cases.evidence_pointers` (JSONB) column in PostgreSQL.
* When downstream microservices (like **AI Summary Service** or **Audit Trail Service**) need clinical details, they use the shared `libs/evidence-lookup/` client to load the JSON file from the path specified in `evidence_pointers`.
* In production, the file paths in `evidence_pointers` will be swapped with S3/MinIO bucket URIs without changing downstream service logic.

---

## Sample Test Cases

| Case ID | Type | Provider / Facility | Risk Score | Key Flag / Issue |
| :--- | :--- | :--- | :--- | :--- |
| **`CASE-2026-001`** | Outpatient | Dr. Robert Vance, MD / Memorial Health System | **850** | CPT 99215 + Modifier 25 unbundled with routine ECG (93000) |
| **`CASE-2026-002`** | Inpatient | Dr. Arthur Pendelton, MD / St. Peter General Hospital | **920** | Knee Arthroplasty upcoded to MS-DRG 469 with unsupported MCC |
