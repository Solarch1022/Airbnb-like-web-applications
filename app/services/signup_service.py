"""Business logic for starting user signup."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.email_verification_dao import (
    EmailVerificationDAO,
    get_email_verification_dao,
)
from app.models.auth import EmailVerification, VerificationStatus
from app.services.email_service import EmailService, get_email_service


class SignupService:
    """Service responsible for starting the signup workflow."""

    OTP_EXPIRY_MINUTES = 10

    def __init__(
        self,
        account_dao: AccountDAO,
        verification_dao: EmailVerificationDAO,
        email_service: EmailService,
    ) -> None:
        self._account_dao = account_dao
        self._verification_dao = verification_dao
        self._email_service = email_service

    def start_signup(self, email: str) -> None:
        """Start signup by generating and sending an email verification code."""

        normalized_email = email.strip().lower()

        existing_account = self._account_dao.get_account_by_email(
            normalized_email
        )

        if existing_account is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        otp = self._generate_otp()
        code_hash = self._hash_otp(otp)

        now = datetime.now(timezone.utc)

        verification = EmailVerification(
            email=normalized_email,
            code_hash=code_hash,
            status=VerificationStatus.PENDING,
            expires_at=now + timedelta(
                minutes=self.OTP_EXPIRY_MINUTES
            ),
            attempt_count=0,
            created_at=now,
        )

        self._verification_dao.put_verification(
            verification.model_dump(),
        )

        self._email_service.send_verification_code(
            email=normalized_email,
            code=otp,
        )

    @staticmethod
    def _generate_otp() -> str:
        """Generate a cryptographically secure six-digit OTP."""
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def _hash_otp(code: str) -> str:
        """Hash an OTP before storing it."""
        return hashlib.sha256(
            code.encode("utf-8")
        ).hexdigest()


def get_signup_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    verification_dao: EmailVerificationDAO = Depends(
        get_email_verification_dao
    ),
    email_service: EmailService = Depends(get_email_service),
) -> SignupService:
    """Dependency provider for SignupService."""
    return SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
    )