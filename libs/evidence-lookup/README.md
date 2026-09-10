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
