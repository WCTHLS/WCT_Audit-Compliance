"""
Pre-defined test tokens and mock users for local POC development, curl, and frontend testing.
"""

import argparse
from typing import Dict
from auth_middleware.jwt_handler import create_jwt_token
from auth_middleware.models import AuthenticatedUser, UserRoleEnum

# Predefined user profiles for POC
TEST_USERS: Dict[str, AuthenticatedUser] = {
    "auditor": AuthenticatedUser(
        user_id="auditor-01",
        name="Sarah Jenkins, RN - Lead Auditor",
        email="auditor.jenkins@wct-payer.com",
        role=UserRoleEnum.AUDITOR,
    ),
    "provider": AuthenticatedUser(
        user_id="provider-billing-01",
        name="Memorial Hospital Billing & RCM Dept",
        email="billing@memorial-health.org",
        role=UserRoleEnum.PROVIDER,
        facility_npi="1295847361",
    ),
    "system": AuthenticatedUser(
        user_id="system-orchestrator",
        name="Temporal Workflow Engine",
        email="system@wct-internal.local",
        role=UserRoleEnum.SYSTEM,
    ),
}


def get_test_token(profile_name: str) -> str:
    """Generate a valid JWT token for a named test profile ('auditor', 'provider', or 'system')."""
    profile = TEST_USERS.get(profile_name.lower())
    if not profile:
        raise ValueError(f"Unknown test profile: '{profile_name}'. Available: {list(TEST_USERS.keys())}")

    return create_jwt_token(
        user_id=profile.user_id,
        role=profile.role,
        name=profile.name,
        email=profile.email,
        facility_npi=profile.facility_npi,
        expires_in_hours=720,  # 30 days for local development convenience
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate WCT Dev JWT Auth Tokens")
    parser.add_argument(
        "--profile",
        "-p",
        choices=["auditor", "provider", "system"],
        default="auditor",
        help="Test user profile to generate token for",
    )
    args = parser.parse_args()

    token = get_test_token(args.profile)
    user = TEST_USERS[args.profile]
    print(f"\n--- Generated Token for [{args.profile.upper()}] ---")
    print(f"User ID : {user.user_id}")
    print(f"Name    : {user.name}")
    print(f"Role    : {user.role.value}")
    if user.facility_npi:
        print(f"Facility: NPI {user.facility_npi}")
    print(f"\nBearer Token:\n{token}\n")
