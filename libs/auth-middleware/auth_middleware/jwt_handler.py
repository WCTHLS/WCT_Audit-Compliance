"""
JWT token encoding, decoding, and validation utilities.
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Any, Dict, Optional
import jwt
from pydantic import ValidationError

from auth_middleware.models import AuthenticatedUser, UserRoleEnum

# Dev/POC default secret key (can be overridden via environment variable)
DEFAULT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "wct-audit-compliance-dev-secret-key-2026")
ALGORITHM = "HS256"
DEFAULT_EXPIRY_HOURS = 24


class AuthError(Exception):
    """Base exception for authentication failures."""
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_jwt_token(
    user_id: str,
    role: UserRoleEnum | str,
    name: str,
    email: Optional[str] = None,
    facility_npi: Optional[str] = None,
    expires_in_hours: int = DEFAULT_EXPIRY_HOURS,
    secret_key: str = DEFAULT_SECRET_KEY,
) -> str:
    """
    Generate a signed JWT token for testing, frontend login, or inter-service auth.
    """
    if isinstance(role, str):
        role = UserRoleEnum(role.upper())

    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": user_id,
        "role": role.value,
        "name": name,
        "email": email,
        "facility_npi": facility_npi,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_in_hours)).timestamp()),
    }

    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_jwt_token(
    token: str,
    secret_key: str = DEFAULT_SECRET_KEY,
) -> AuthenticatedUser:
    """
    Decode and validate a JWT token string. Returns AuthenticatedUser on success.
    Raises AuthError on expired, malformed, or invalid tokens.
    """
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return AuthenticatedUser(
            user_id=payload.get("sub", ""),
            role=UserRoleEnum(payload.get("role", "").upper()),
            name=payload.get("name", ""),
            email=payload.get("email"),
            facility_npi=payload.get("facility_npi"),
        )
    except jwt.ExpiredSignatureError:
        raise AuthError("JWT token has expired", status_code=401)
    except (jwt.InvalidTokenError, ValidationError, ValueError) as e:
        raise AuthError(f"Invalid authentication token: {str(e)}", status_code=401)
