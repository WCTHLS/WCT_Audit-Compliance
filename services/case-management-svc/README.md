# Case Management Service (`services/case-management-svc/`)

The **Case Management Service** is the central system of record for **WCT Module 5 (Audit & Compliance Workflow)**.

## Responsibilities
- Owns the `cases` PostgreSQL table and lifecycle states (`NEW` -> `ENRICHING` -> `READY_FOR_REVIEW` -> `DECISION_RECORDED` -> `CLOSED`).
- Ingests `case.created` events from Kafka and establishes the initial 72-hour SLA clock.
- Stores `evidence_pointers` (JSONB) linking cases to clinical evidence, SHAP risk factors, and peer comparison data.
- Provides CRUD APIs (`POST /cases`, `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}`) for the Auditor Workbench.
