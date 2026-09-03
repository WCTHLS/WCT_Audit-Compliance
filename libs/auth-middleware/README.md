# WCT Auth Middleware (`libs/auth-middleware`)

Lightweight JWT authentication and Role-Based Access Control (RBAC) middleware for **Module 5: Audit & Compliance**.

## Overview

Provides stateless token validation and FastAPI route guards without requiring external identity providers during POC development.

### Supported Roles & User Types
1. **`AUDITOR`**: Clinical claim auditor reviewing cases in the **Auditor Workbench**.
2. **`PROVIDER`**: Hospital billing coordinator / clinic admin responding to document requests in the **Provider Portal**.
3. **`SYSTEM`**: Internal background orchestrators (Temporal workflows).

---

## Installation

```bash
pip install -e libs/auth-middleware
```

---

## Usage in FastAPI Services

```python
from fastapi import APIRouter, Depends
from auth_middleware import (
    AuthenticatedUser,
    UserRoleEnum,
    get_current_user,
    require_role,
    require_any_role,
)

router = APIRouter()

# 1. Any authenticated user:
@router.get("/cases/{case_id}")
def get_case(case_id: str, user: AuthenticatedUser = Depends(get_current_user)):
    return {"case_id": case_id, "user": user.user_id, "role": user.role.value}

# 2. Auditor-only endpoint:
@router.post("/cases/{case_id}/decision")
def submit_decision(
    case_id: str,
    user: AuthenticatedUser = Depends(require_role(UserRoleEnum.AUDITOR)),
):
    return {"status": "Decision recorded", "by": user.user_id}

# 3. Provider-only endpoint (e.g. upload documents):
@router.post("/cases/{case_id}/documents")
def upload_docs(
    case_id: str,
    user: AuthenticatedUser = Depends(require_role(UserRoleEnum.PROVIDER)),
):
    return {"status": "Docs uploaded", "facility_npi": user.facility_npi}
```

---

## Generating Test Tokens

Generate ready-to-use JWT Bearer tokens for curl requests or React UI testing:

```bash
# Generate token for Auditor
python -m auth_middleware.test_tokens --profile auditor

# Generate token for Provider Staff
python -m auth_middleware.test_tokens --profile provider

# Generate token for System Orchestrator
python -m auth_middleware.test_tokens --profile system
```

---

## Running Tests

```bash
pytest libs/auth-middleware/tests/
```
