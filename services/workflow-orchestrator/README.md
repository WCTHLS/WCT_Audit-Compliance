# WCT Workflow Orchestrator Service

Temporal-based durable workflow orchestration for **WCT Module 5: Audit & Compliance Workflow**.

## Responsibilities
- Coordinates the lifecycle of a case audit from creation to final decision.
- Manages long-running timers (72h human-in-the-loop SLA confirmation window).
- Dispatches parallel activities (AI case summary, exclusion screening, risk factor calculations).
- Emits decision events and triggers immutable audit logging upon case resolution.

## Architecture
- **Framework:** Temporal Python SDK (`temporalio`)
- **Queue:** `wct-case-audit-queue`
- **Default Temporal Server:** `localhost:7233` (Docker: `temporal:7233`)
- **Temporal Web UI:** `http://localhost:8233`
