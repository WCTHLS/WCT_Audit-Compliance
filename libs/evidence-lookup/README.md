# WCT Evidence Lookup Client (`libs/evidence-lookup/`)

Shared Python library for resolving healthcare audit case `evidence_pointers` into strongly typed clinical, risk model, and peer distribution data structures.

## Purpose
- In WCT Module 5, the primary PostgreSQL `cases` table stores lightweight `evidence_pointers` (JSONB) referencing upstream/mock evidence files rather than storing heavy clinical records and ML arrays directly in table rows.
- The **`EvidenceLookupClient`** acts as a unified data-access layer used by downstream microservices (`ai-summary-svc`, `workflow-orchestrator`, `auditor-workbench`) to resolve pointers into validated data models.

## Usage
```python
from evidence_lookup import EvidenceLookupClient

client = EvidenceLookupClient()

# Resolve clinical notes and claim lines
clinical_data = client.resolve_clinical_evidence(case.evidence_pointers)

# Resolve SHAP explainability & risk factors
risk_data = client.resolve_risk_factors(case.evidence_pointers)

# Resolve full evidence bundle
bundle = client.resolve_all(case.evidence_pointers)
```

## Schema Resilience & Production Tradeoffs
- **Lenient Ingestion (`extra="allow"` + `Optional`):** All models in `evidence_lookup.models` allow unexpected attributes and default missing fields to `None`. This provides tolerance across diverse upstream data formats and partial mock evidence bundles.
- **Production Warning:** Misspelled field keys (e.g. `billed_ammount` vs `billed_amount`) will pass through without raising a `ValidationError` and remain in `__pydantic_extra__`, leaving canonical attributes as `None`. For production deployments:
  - Enforce producer-side schema contracts at the message broker / ingestion boundary.
  - Implement Pydantic `AliasChoices` for known upstream naming variations.
  - Log warnings if core financial metrics evaluate to `None` while extra payload fields exist.

