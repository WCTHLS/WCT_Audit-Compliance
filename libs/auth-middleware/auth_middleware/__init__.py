"""
WCT Auth Middleware Package.
Stub JWT authentication and RBAC for Module 5 microservices.
"""

from auth_middleware.dependencies import (
    get_current_user,
    require_any_role,
    require_role,
)
from auth_middleware.jwt_handler import (
    AuthError,
    create_jwt_token,
    decode_jwt_token,
)
from auth_middleware.models import (
    AuthenticatedUser,
    UserRoleEnum,
)
from auth_middleware.test_tokens import (
    TEST_USERS,
    get_test_token,
)

__all__ = [
    "AuthError",
    "AuthenticatedUser",
    "TEST_USERS",
    "UserRoleEnum",
    "create_jwt_token",
    "decode_jwt_token",
    "get_current_user",
    "get_test_token",
    "require_any_role",
    "require_role",
]
