# WCT Event Contracts (`libs/event-contracts`)

Shared data contracts, Pydantic v2 models, and JSON Schemas for **Module 5: Audit & Compliance Workflow**.

## Overview

This library defines the strict data contracts for all event-driven interactions in Module 5:
1. **`CaseCreatedEvent` (`case.created`)**: Data ingress contract published by FWA Detection when a claim is flagged for audit.
2. **`CaseStatusChangedEvent` (`case.status.changed`)**: Internal event fired on every case state transition to update the OpenSearch queue, trigger notification alerts, and record audit trail history.

---

## Installation

```bash
pip install -e libs/event-contracts
```

---

## Usage

### Ingesting / Producing `CaseCreatedEvent`

```python
from datetime import date
from event_contracts import CaseCreatedEvent, EvidencePointers, PeerComparisonData

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
    risk_score=850,  # Scale: 100-1000 (>= 500 is risky)
    flagged_reason="Excessive billing of CPT 99215 with modifier 25",
    evidence_pointers=EvidencePointers(
        clinical_evidence="mock-data/fwa-mock/case_001_clinical_evidence.json",
        risk_factors="mock-data/fwa-mock/case_001_risk_factors.json",
        peer_comparison=PeerComparisonData(
            specialty="Interventional Cardiology",
            region="US-Northeast",
            cohort_size=184,
            provider_metric_value=4.8,
            peer_median=1.2,
            fixture_ref="mock-data/fwa-mock/case_001_peer_comparison.json",
        ),
        claim_flags="mock-data/pi-mock/case_001_claim_flags.json",
    ),
)

# Convert to JSON for Kafka / Redpanda publishing:
kafka_payload = event.model_dump_json()
```

### Transitioning State with `CaseStatusChangedEvent`

```python
from datetime import datetime, timezone
from event_contracts import (
    AuditDecisionEnum,
    CaseStatusChangedEvent,
    CaseStatusEnum,
    DecisionSummary,
    SlaTypeEnum,
)

status_event = CaseStatusChangedEvent(
    case_id="CASE-2026-001",
    claim_ref="CLM-99214-8841",
    previous_status=CaseStatusEnum.READY_FOR_REVIEW,
    new_status=CaseStatusEnum.DECISION_RECORDED,
    changed_by="auditor-01",
    changed_by_role="Auditor",
    sla_type=SlaTypeEnum.INITIAL_REVIEW,
    sla_breached=False,
    decision_summary=DecisionSummary(
        decision=AuditDecisionEnum.UPHOLD,
        rationale="Modifier 25 unbundled without separate distinct E&M documentation.",
        regulatory_basis="CMS NCCI Policy Manual Chapter 1",
    ),
)
```

---

## Exporting JSON Schemas

To export the raw `.json` JSON Schema definitions for schema registries or non-Python consumers:

```bash
python -m event_contracts.export_schemas
```
Exported schemas will be saved to `libs/event-contracts/event_contracts/schemas/`.

---

## Running Tests

```bash
pytest libs/event-contracts/tests/
```
