from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class AccountStatus(str, Enum):
    UNVERIFIED = "unverified"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"


class AccountCreate(BaseModel):
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

    status: AccountStatus = AccountStatus.UNVERIFIED


class AccountUpdate(BaseModel):
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


class Account(BaseModel):
    id: str
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

    status: AccountStatus
    created_at: datetime
    updated_at: datetime