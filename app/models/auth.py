from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    LOCKED = "locked"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class VerificationChannel(str, Enum):
    EMAIL = "email"
    PHONE = "phone"


class VerificationPurpose(str, Enum):
    SIGNUP = "signup"


class SignupRequest(BaseModel):
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


class SignupResponse(BaseModel):
    message: str


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
    )


class OTPVerification(BaseModel):
    identifier: str
    channel: VerificationChannel
    purpose: VerificationPurpose

    code_hash: str
    status: VerificationStatus

    attempt_count: int = 0
    resend_count: int = 0

    created_at: datetime
    expires_at: datetime
    last_sent_at: datetime
    session_expires_at: datetime