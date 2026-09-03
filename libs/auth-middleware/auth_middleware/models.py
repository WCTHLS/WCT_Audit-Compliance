"""
User identity models and role definitions for WCT Module 5.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserRoleEnum(str, Enum):
    """
    Standard roles across the Audit & Compliance ecosystem.
    """
    AUDITOR = "AUDITOR"       # Clinical Claim Auditor (Auditor Workbench)
    PROVIDER = "PROVIDER"     # Hospital Billing / Clinic Admin (Provider Portal)
    SYSTEM = "SYSTEM"         # Automated backend workers (Temporal / Cron)


class AuthenticatedUser(BaseModel):
    """
    User context extracted from the validated JWT token or stub profile.
    Injected into FastAPI endpoint handlers via dependencies.
    """
    model_config = ConfigDict(extra="ignore")

    user_id: str = Field(..., description="Unique user or service identifier (e.g. auditor-01)")
    email: Optional[str] = Field(None, description="User email address")
    name: str = Field(..., description="Full display name (e.g. Sarah Jenkins, RN)")
    role: UserRoleEnum = Field(..., description="Assigned primary role (AUDITOR, PROVIDER, SYSTEM)")
    facility_npi: Optional[str] = Field(None, description="10-digit Hospital/Facility NPI if role is PROVIDER")
    is_active: bool = Field(default=True, description="Account active status")
