"""
FastAPI dependencies for JWT authentication and Role-Based Access Control (RBAC).
"""

from typing import Callable, List, Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth_middleware.jwt_handler import AuthError, decode_jwt_token
from auth_middleware.models import AuthenticatedUser, UserRoleEnum

http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    authorization: Optional[str] = Header(None, description="Format: Bearer <jwt-token>"),
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts and validates the JWT Bearer token.
    Supports OpenAPI Swagger Authorize button via HTTPBearer, as well as explicit Authorization header.
    Returns AuthenticatedUser on success, or raises 401 Unauthorized.
    """
    token: Optional[str] = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Authorization header format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_jwt_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(required_role: UserRoleEnum | str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """
    FastAPI dependency factory that enforces a specific role (e.g. AUDITOR or PROVIDER).
    Raises 403 Forbidden if user does not possess the role.
    """
    if isinstance(required_role, str):
        required_role = UserRoleEnum(required_role.upper())

    def _role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires '{required_role.value}' role, but user has '{user.role.value}'.",
            )
        return user

    return _role_checker


def require_any_role(*allowed_roles: UserRoleEnum | str) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """
    FastAPI dependency factory that allows access if user has ANY of the specified roles.
    """
    normalized_roles = [
        r if isinstance(r, UserRoleEnum) else UserRoleEnum(r.upper())
        for r in allowed_roles
    ]

    def _any_role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if user.role not in normalized_roles:
            allowed_names = [r.value for r in normalized_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of {allowed_names}, but user has '{user.role.value}'.",
            )
        return user

    return _any_role_checker
