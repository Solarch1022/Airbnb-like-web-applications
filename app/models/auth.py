"""Models used by authentication and user onboarding flows."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class VerificationStatus(str, Enum):
    """Status of an email verification request."""

    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"


class SignupRequest(BaseModel):
    """Request payload for starting signup."""

    email: EmailStr


class SignupResponse(BaseModel):
    """Response returned after signup has started."""

    message: str


class EmailVerification(BaseModel):
    """Stored email verification record."""

    email: EmailStr

    code_hash: str = Field(..., min_length=1)

    status: VerificationStatus = VerificationStatus.PENDING

    expires_at: datetime

    attempt_count: int = Field(default=0, ge=0)

    created_at: datetime