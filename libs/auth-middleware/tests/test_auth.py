"""
Unit tests for auth_middleware (JWT creation, decoding, expiration, FastAPI dependencies, RBAC).
"""

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from auth_middleware import (
    AuthError,
    AuthenticatedUser,
    UserRoleEnum,
    create_jwt_token,
    decode_jwt_token,
    get_current_user,
    get_test_token,
    require_any_role,
    require_role,
)


def test_jwt_encode_and_decode_valid():
    """Verify standard JWT encoding and decoding round-trip."""
    token = create_jwt_token(
        user_id="auditor-01",
        role=UserRoleEnum.AUDITOR,
        name="Sarah Jenkins",
        email="sjenkins@payer.org",
    )
    user = decode_jwt_token(token)

    assert user.user_id == "auditor-01"
    assert user.role == UserRoleEnum.AUDITOR
    assert user.name == "Sarah Jenkins"
    assert user.email == "sjenkins@payer.org"
    assert user.is_active is True


def test_provider_token_with_facility_npi():
    """Verify provider token encodes and extracts hospital facility NPI."""
    token = create_jwt_token(
        user_id="prov-staff-1",
        role="PROVIDER",
        name="Memorial Billing Dept",
        facility_npi="1295847361",
    )
    user = decode_jwt_token(token)

    assert user.user_id == "prov-staff-1"
    assert user.role == UserRoleEnum.PROVIDER
    assert user.facility_npi == "1295847361"


def test_jwt_expired_token():
    """Verify expired token raises AuthError with 401 status."""
    token = create_jwt_token(
        user_id="auditor-old",
        role=UserRoleEnum.AUDITOR,
        name="Old User",
        expires_in_hours=-1,  # Expired in past
    )
    with pytest.raises(AuthError) as exc_info:
        decode_jwt_token(token)
    assert "expired" in str(exc_info.value).lower()
    assert exc_info.value.status_code == 401


def test_jwt_invalid_signature():
    """Verify token signed with a different secret is rejected."""
    token = create_jwt_token(
        user_id="auditor-fake",
        role=UserRoleEnum.AUDITOR,
        name="Fake User",
        secret_key="secret-key-A-must-be-at-least-32-chars-long!",
    )
    with pytest.raises(AuthError):
        decode_jwt_token(token, secret_key="secret-key-B-must-be-at-least-32-chars-long!")


def test_test_tokens_helper():
    """Verify pre-defined profiles generate valid tokens."""
    for profile in ["auditor", "provider", "system"]:
        token = get_test_token(profile)
        user = decode_jwt_token(token)
        assert user.role.value.lower() == profile


# --- FastAPI Integration Tests ---

app = FastAPI()

@app.get("/public")
def public_endpoint():
    return {"message": "public"}

@app.get("/me")
def me_endpoint(user: AuthenticatedUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "role": user.role.value}

@app.post("/auditor-only")
def auditor_action(user: AuthenticatedUser = Depends(require_role(UserRoleEnum.AUDITOR))):
    return {"status": "auditor action accepted", "auditor": user.user_id}

@app.post("/provider-only")
def provider_action(user: AuthenticatedUser = Depends(require_role("PROVIDER"))):
    return {"status": "provider action accepted", "npi": user.facility_npi}

@app.get("/any-role")
def any_action(user: AuthenticatedUser = Depends(require_any_role(UserRoleEnum.AUDITOR, UserRoleEnum.SYSTEM))):
    return {"status": "allowed"}

client = TestClient(app)


def test_fastapi_unauthorized_missing_header():
    """Endpoint requiring auth returns 401 when Authorization header is omitted."""
    resp = client.get("/me")
    assert resp.status_code == 401


def test_fastapi_unauthorized_invalid_header_format():
    """Endpoint returns 401 on malformed Authorization header."""
    resp = client.get("/me", headers={"Authorization": "Token 12345"})
    assert resp.status_code == 401


def test_fastapi_authenticated_success():
    """Endpoint returns 200 and user info with valid token."""
    token = get_test_token("auditor")
    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "auditor-01"
    assert resp.json()["role"] == "AUDITOR"


def test_fastapi_rbac_forbidden():
    """Provider attempting an auditor-only endpoint receives 403 Forbidden."""
    token = get_test_token("provider")
    resp = client.post("/auditor-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]


def test_fastapi_rbac_allowed():
    """Auditor attempting auditor-only endpoint succeeds."""
    token = get_test_token("auditor")
    resp = client.post("/auditor-only", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "auditor action accepted"
