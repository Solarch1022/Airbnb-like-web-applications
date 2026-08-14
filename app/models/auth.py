from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class VerificationStatus(str, Enum):

    PENDING = "pending"
    VERIFIED = "verified"
    EXPIRED = "expired"


class SignupRequest(BaseModel):
    email: EmailStr


class SignupResponse(BaseModel):
    message: str

class VerificationChannel(str, Enum):
    EMAIL = "email"
    PHONE = "phone"

class OTPVerification(BaseModel):
    identifier: str
    channel: VerificationChannel
    code_hash: str
    status: VerificationStatus = VerificationStatus.PENDING
    expires_at: datetime
    attempt_count: int = 0
    created_at: datetime