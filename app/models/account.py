from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class AccountStatus(str, Enum):

    PENDING = "pending"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    DELETED = "deleted"


class AccountBase(BaseModel):

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
    pass


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


class Account(AccountBase):

    id: str
    created_at: datetime
    updated_at: datetime