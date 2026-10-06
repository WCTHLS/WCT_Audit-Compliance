# WCT Exclusion Screening Service (`exclusion-screening-svc`)

Microservice for **WCT Module 5 (Audit & Compliance Workflow)**.  
Screens healthcare providers, billing facilities, and associated entities against the federal **HHS-OIG List of Excluded Individuals/Entities (LEIE)** and synthetic test exclusion overlays to prevent improper payments to barred entities.

---

## 🌟 Key Capabilities

* **Multi-Entity Screening**:
  * Screens ordering/attending physicians by **NPI** and normalized name.
  * Screens billing facilities and organizational entities by **Facility NPI** and business name.
  * Resolves and screens associated fraud-ring entities and co-conspirators from case evidence pointers.
* **Deterministic Match Classification**:
  * **`MATCH`**: Exact 10-digit NPI match or exact normalized full name match.
  * **`POSSIBLE_MATCH`**: High-confidence fuzzy name match or partial attribute match (requires auditor manual confirmation).
  * **`NO_MATCH`**: No active federal exclusion records found.
* **Statutory Exclusion Details**:
  * Returns statutory exclusion authority (e.g., *1128(a)(1) - Program-related crimes*, *1128(b)(4) - License revocation*), exclusion effective date, provider specialty, and geographic location.
* **Snapshot Versioning & Telemetry**:
  * Tracks dataset versions (e.g., active OIG LEIE monthly snapshot vs. synthetic overlay) and record counts via `/health`.

---

## 🏗️ Architecture & Stack

* **Framework**: FastAPI + Pydantic v2 + Uvicorn
* **Database**: PostgreSQL (`exclusion_records` table) + SQLAlchemy 2.0 ORM
* **Port**: `8002` (configured in `infra/docker-compose.dev.yml`)
* **Container**: `audit-exclusion-screening-svc`

---

## 🚀 API Specification

### 1. Health Probe (`GET /health`)
Returns service health, database connectivity, and record counts per source.

#### Response (`200 OK`)
```json
{
  "status": "healthy",
  "service": "exclusion-screening-svc",
  "record_counts": {
    "LEIE": 78240,
    "SYNTHETIC": 6
  },
  "snapshot_info": {
    "LEIE": "active",
    "SYNTHETIC": "active"
  },
  "timestamp": "2026-10-06T08:57:40.511591+00:00"
}
```

---

### 2. Screen Case Entities (`POST /screen`)
Screens all provider, facility, and associated entities for a case.

#### Request Payload
```json
{
  "case_id": "CASE-2026-005",
  "claim_ref": "CLM-2026-5590",
  "doctor_npi": "1245093876",
  "doctor_name": "Dr. Leonard Hask, MD",
  "facility_npi": "1982736450",
  "facility_name": "Evergreen Mobility Supply LLC",
  "evidence_pointers": {}
}
```

#### Response (`200 OK`)
```json
{
  "case_id": "CASE-2026-005",
  "overall_result": "MATCH",
  "screened_at": "2026-10-06T08:46:19.703742+00:00",
  "list_snapshot": {
    "LEIE": "active",
    "SYNTHETIC": "active"
  },
  "results": [
    {
      "role": "ordering_provider",
      "name": "Dr. Leonard Hask, MD",
      "npi": "1245093876",
      "result": "MATCH",
      "match_basis": "npi",
      "record": {
        "source": "SYNTHETIC",
        "excl_type": "1128a1",
        "excl_date": "2024-03-15",
        "specialty": "Physical Medicine & Rehabilitation",
        "last_name": "HASK",
        "first_name": "LEONARD",
        "npi": "1245093876",
        "city": "CHICAGO",
        "state": "IL"
      }
    },
    {
      "role": "facility",
      "name": "Evergreen Mobility Supply LLC",
      "npi": "1982736450",
      "result": "NO_MATCH",
      "match_basis": "none",
      "record": null
    }
  ],
  "requires_auditor_confirmation": false
}
```

---

## 📂 Seed Data & Ingestion Jobs

The service imports exclusion records using `jobs/load_exclusions.py`:

```bash
# Load official federal OIG LEIE dataset
python jobs/load_exclusions.py --file seed/UPDATED.csv --source LEIE

# Load synthetic test overlay (e.g. Dr. Leonard Hask, Dr. Arthur Pendelton)
python jobs/load_exclusions.py --file seed/leie_synthetic_overlay.csv --source SYNTHETIC
```

---

## 🧪 Testing

Run unit and integration test suite:

```bash
pytest services/exclusion-screening-svc/tests -v
```
