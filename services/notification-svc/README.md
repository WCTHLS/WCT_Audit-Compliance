# WCT Notification Service (`notification-svc`)

Microservice for **WCT Module 5 (Audit & Compliance Workflow)**.  
Handles dispatching and tracking notifications for SLA breach warnings, automated provider documentation follow-ups (**FR-AUD-03**), auditor queue dispatches, and supervisory escalations.

---

## 🌟 Key Features

* **Pluggable Provider Architecture**:
  * Decouples the API contract from underlying delivery mechanisms.
  * **Console / Logger Provider (POC)**: Formats alerts into human-readable terminal banners and structured JSON logs.
  * **Production Ready**: Drop-in extension points for SMTP (Email), Twilio/SNS (SMS), and webhooks.
* **Core Audit Lifecycle Alerts**:
  * `SLA_BREACH_WARNING`: Proactive early warning when 72h SLA window nears expiry (e.g. 6–12h remaining).
  * `SLA_BREACH`: Formal breach event when 72h SLA timer elapses without resolution.
  * `DOCUMENT_REQUEST_INITIAL`: First medical records request sent to healthcare provider.
  * `DOCUMENT_REQUEST_REMINDER`: Automated follow-up reminder to provider for pending medical records (**FR-AUD-03**).
  * `AUDITOR_ESCALATION`: Escalation sent to team leads/supervisors for unresponsive providers or high-risk claims.
  * `CASE_ASSIGNMENT`: Case assignment notifications to auditor queues.
  * `SYSTEM_ALERT`: Infrastructure and synchronization alerts.
* **In-Memory Audit Buffer**:
  * Tracks recent dispatches in a thread-safe ring buffer for verification and testing.
  * Queryable via `GET /notifications` and `GET /notifications/{id}`.

---

## 🚀 API Specification

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service liveness, active providers, and dispatch telemetry |
| `POST` | `/notify` | Dispatch an alert or reminder |
| `GET` | `/notifications` | Query dispatches with filters (`case_id`, `recipient`, `notification_type`) |
| `GET` | `/notifications/{id}` | Retrieve specific notification details and delivery receipt |
| `DELETE` | `/notifications` | Clear in-memory history (test setup/teardown) |

### Sample Dispatch Request (`POST /notify`)

```json
{
  "recipient": "1093847562",
  "notification_type": "DOCUMENT_REQUEST_REMINDER",
  "channel": "EMAIL",
  "priority": "HIGH",
  "subject": "Reminder #1: Documentation Request Pending for Claim CLM-2026-8841",
  "message": "Please submit operative report and itemized billing within 24 hours.",
  "case_id": "CASE-2026-001",
  "metadata": {
    "provider_npi": "1093847562",
    "reminder_number": 1
  }
}
```

### Sample Response (`200 OK`)

```json
{
  "notification_id": "NOTIF-20261006095211-8D9FF0",
  "status": "DELIVERED",
  "recipient": "1093847562",
  "channel": "EMAIL",
  "notification_type": "DOCUMENT_REQUEST_REMINDER",
  "case_id": "CASE-2026-001",
  "subject": "Reminder #1: Documentation Request Pending for Claim CLM-2026-8841",
  "dispatched_at": "2026-10-06T09:52:11.783472+00:00",
  "provider": "console-logger",
  "details": "Alert dispatched via console-logger simulation.",
  "metadata": {
    "provider_npi": "1093847562",
    "reminder_number": 1
  }
}
```

---

## 🧪 Testing

Run unit and integration test suite:

```bash
pytest services/notification-svc/tests -v
```
