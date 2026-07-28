from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class UserType(str, Enum):
    CUSTOMER = "customer"
    OWNER = "owner"


class EmailInfo(BaseModel):
    email: EmailStr
    is_verified: bool = False


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email_info: list[EmailInfo]
    phone: str | None = Field(default=None, max_length=30)
    credential_id: str | None = None
    type: UserType


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email_info: list[EmailInfo] | None = None
    phone: str | None = Field(default=None, max_length=30)
    credential_id: str | None = None
    type: UserType | None = None


class User(BaseModel):
    id: str
    name: str
    email_info: list[EmailInfo]
    phone: str | None = None
    credential_id: str | None = None
    type: UserType