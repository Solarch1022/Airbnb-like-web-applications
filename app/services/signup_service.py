from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.otp_verification_dao import (
    OTPVerificationDAO,
    get_otp_verification_dao,
)
from app.models.account import Account, AccountStatus
from app.models.auth import (
    OTPVerification,
    VerificationChannel,
    VerificationPurpose,
    VerificationStatus,
)
from app.services.email_service import EmailService, get_email_service
from app.services.otp_service import OTPService, get_otp_service


class SignupService:

    OTP_EXPIRY_MINUTES = 10
    SIGNUP_SESSION_EXPIRY_MINUTES = 60
    RESEND_COOLDOWN_SECONDS = 60

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

        now = datetime.now(timezone.utc)

        existing_verification = None

        if existing_account is None:
            account = Account(
                id=str(uuid4()),
                email=normalized_email,
                status=AccountStatus.UNVERIFIED,
                created_at=now,
                updated_at=now,
            )

            self._account_dao.put_account(account)

        elif existing_account.status == AccountStatus.UNVERIFIED:
            existing_verification = self._verification_dao.get_verification(
                normalized_email,
                VerificationPurpose.SIGNUP,
            )

            if existing_verification is not None:
                if existing_verification.session_expires_at <= now:
                    existing_verification = None

                elif existing_verification.status == VerificationStatus.LOCKED:
                    return

                else:
                    cooldown_until = existing_verification.last_sent_at + timedelta(
                        seconds=self.RESEND_COOLDOWN_SECONDS
                    )
                    if now < cooldown_until:
                        return

        else:
            return
        
        otp = self._otp_service.generate()
        code_hash = self._otp_service.hash(otp)

        if existing_verification is None:
            verification = OTPVerification(
                identifier=normalized_email,
                channel=VerificationChannel.EMAIL,
                purpose=VerificationPurpose.SIGNUP,
                code_hash=code_hash,
                status=VerificationStatus.PENDING,
                attempt_count=0,
                resend_count=0,
                created_at=now,
                expires_at=now + timedelta(
                    minutes=self.OTP_EXPIRY_MINUTES
                ),
                last_sent_at=now,
                session_expires_at=now + timedelta(
                    minutes=self.SIGNUP_SESSION_EXPIRY_MINUTES
                ),
            )

        else:
            verification = existing_verification.model_copy(
                update={
                    "code_hash": code_hash,
                    "resend_count": existing_verification.resend_count + 1,
                    "expires_at": now + timedelta(
                        minutes=self.OTP_EXPIRY_MINUTES
                    ),
                    "last_sent_at": now,
                }
            )

        self._verification_dao.put_verification(
            verification,
        )

        self._email_service.send_verification_code(
            email=normalized_email,
            code=otp,
        )

    def verify_signup_otp(
            self,
            email: str,
            code: str,
        ) -> bool:
            normalized_email = email.strip().lower()

            verification = self._verification_dao.get_verification(
                normalized_email,
                VerificationPurpose.SIGNUP,
            )

            if verification is None:
                return False

            if verification.status != VerificationStatus.PENDING:
                return False

            now = datetime.now(timezone.utc)

            if now >= verification.session_expires_at:
                return False

            if now >= verification.expires_at:
                return False

            if not self._otp_service.verify(
                code=code,
                code_hash=verification.code_hash,
            ):
                self._verification_dao.record_failed_attempt(
                    identifier=normalized_email,
                    purpose=VerificationPurpose.SIGNUP,
                )
                return False

            account = self._account_dao.get_account_by_email(
                normalized_email
            )

            if account is None:
                return False

            if account.status != AccountStatus.UNVERIFIED:
                return False

            updated_account = account.model_copy(
                update={
                    "status": AccountStatus.ACTIVE,
                    "updated_at": now,
                }
            )

            self._account_dao.put_account(updated_account)

            consumed_verification = verification.model_copy(
                update={
                    "status": VerificationStatus.CONSUMED,
                }
            )

            self._verification_dao.update_verification(
                consumed_verification
            )

            return True

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