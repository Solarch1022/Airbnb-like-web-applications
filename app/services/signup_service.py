from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.otp_verification_dao import (
    OTPVerificationDAO,
    get_otp_verification_dao,
)
from app.models.auth import (
    OTPVerification,
    VerificationChannel,
    VerificationStatus,
)
from app.services.email_service import EmailService, get_email_service
from app.services.otp_service import OTPService, get_otp_service


class SignupService:

    OTP_EXPIRY_MINUTES = 10

    def __init__(
        self,
        account_dao: AccountDAO,
        verification_dao: OTPVerificationDAO,
        email_service: EmailService,
        otp_service: OTPService,
    ) -> None:
        self._account_dao = account_dao
        self._verification_dao = verification_dao
        self._email_service = email_service
        self._otp_service = otp_service

    def start_signup(self, email: str) -> None:

        normalized_email = email.strip().lower()

        existing_account = self._account_dao.get_account_by_email(
            normalized_email
        )

        if existing_account is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        otp = self._otp_service.generate()
        code_hash = self._otp_service.hash(otp)

        now = datetime.now(timezone.utc)

        verification = OTPVerification(
            identifier=normalized_email,
            channel=VerificationChannel.EMAIL,
            code_hash=code_hash,
            status=VerificationStatus.PENDING,
            expires_at=now + timedelta(
                minutes=self.OTP_EXPIRY_MINUTES
            ),
            attempt_count=0,
            created_at=now,
        )

        self._verification_dao.put_verification(
            verification,
        )

        self._email_service.send_verification_code(
            email=normalized_email,
            code=otp,
        )


def get_signup_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    verification_dao: OTPVerificationDAO = Depends(
        get_otp_verification_dao
    ),
    email_service: EmailService = Depends(get_email_service),
    otp_service: OTPService = Depends(get_otp_service),
) -> SignupService:
    return SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )