"""Models for user accounts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class AccountStatus(str, Enum):
    """Supported account statuses."""

    PENDING = "pending"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class AccountBase(BaseModel):
    """Shared account fields."""

    email: EmailStr

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    status: AccountStatus = AccountStatus.PENDING


class AccountCreate(AccountBase):
    """Payload used internally to create an account."""


class AccountUpdate(BaseModel):
    """Payload used to update account profile data."""

    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    status: AccountStatus | None = None


class Account(AccountBase):
    """Stored account representation."""

    id: str
    created_at: datetime
    updated_at: datetime