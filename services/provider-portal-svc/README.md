# Provider Portal Service (`provider-portal-svc`)

**Layer**: API Layer  
**Service Port**: `8005` (API)  
**Package**: `services/provider-portal-svc`  
**Purpose**: Handles auditor documentation requests to healthcare providers, tracks read receipts, and receives submitted provider medical records and responses for WCT Module 5 (Audit & Compliance Workflow).

---

## Features

1. **Auditor Document Requests (`POST /document-requests`)**:
   * Auditor submits a request for clinical documentation on a specific case.
   * Tracks requested document types, target due dates, and special instructions.
   * Generates a unique tracking identifier (`DOCREQ-YYYYMMDDHHMMSS-XXXXXX`).

2. **Read Receipts Tracking (`POST /document-requests/{id}/read`)**:
   * Timestamps when the provider first opened/viewed the request (`read_at`).
   * Tracks total view count (`read_count`) and most recent view timestamp (`last_read_at`).
   * Transitions status from `REQUESTED` to `VIEWED`.
   * Directly feeds automated follow-up reminder logic (distinguishing unread/unopened notices from opened but pending submissions).

3. **Provider Responses (`POST /document-requests/{id}/respond`)**:
   * Provider submits clinical justification notes and attached document references.
   * Transitions status to `RESPONDED` with recorded submission timestamps.

4. **Case & Provider Filtering**:
   * Filter requests by `case_id` (`GET /document-requests/case/{case_id}`).
   * Filter requests by `provider_npi` (`GET /document-requests/provider/{provider_npi}`).

---

## Lifecycle States

```
[Auditor Creates Request]
         │
         ▼
     REQUESTED  ────── (Provider Opens Request) ──────►  VIEWED
         │                                                 │
         │                                                 │
         ├─────────────────── (Provider Submits Response) ─┤
         ▼                                                 ▼
     RESPONDED                                         RESPONDED
         ▲
         │ (Auditor can cancel if needed)
     CANCELLED
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Liveness probe and total stored requests count |
| `POST` | `/document-requests` | Auditor creates a new document request |
| `GET` | `/document-requests` | List all requests with lifecycle summary counts |
| `GET` | `/document-requests/{id}` | Get full details of a specific request |
| `GET` | `/document-requests/case/{case_id}` | List all requests for an audit case |
| `GET` | `/document-requests/provider/{npi}` | List all requests directed to a provider |
| `POST` | `/document-requests/{id}/read` | Record a read receipt when provider opens request |
| `POST` | `/document-requests/{id}/respond` | Provider submits clinical notes and attachments |
| `POST` | `/document-requests/{id}/reminder` | Record automated follow-up reminder dispatch |
| `POST` | `/document-requests/{id}/cancel` | Auditor cancels a pending request |

---

## Testing

Run automated tests via `pytest`:

```powershell
& ".\.venv\Scripts\pytest.exe" services/provider-portal-svc/tests -v
```
