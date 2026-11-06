from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class OrganisationStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class OrganisationRole(str, Enum):
    ADMIN = "admin"
    MEMBER = "member"


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class OrganisationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class Organisation(BaseModel):
    organisation_id: str
    name: str
    status: OrganisationStatus
    created_by: str
    created_at: datetime
    updated_at: datetime


class Membership(BaseModel):
    organisation_id: str
    account_id: str
    role: OrganisationRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime


class OrganisationContext(BaseModel):
    organisation: Organisation
    membership: Membership
