import hashlib
import secrets

from datetime import datetime, timedelta

from app.models.auth import (
    OTPVerification,
    VerificationChannel,
    VerificationPurpose,
    VerificationStatus,
)


class OTPService:
    OTP_EXPIRY_MINUTES = 10
    SIGNUP_SESSION_EXPIRY_MINUTES = 60
    RESEND_COOLDOWN_SECONDS = 60

    def generate(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def hash(self, code: str) -> str:
        return hashlib.sha256(
            code.encode("utf-8")
        ).hexdigest()

    def verify(
        self,
        code: str,
        code_hash: str,
    ) -> bool:
        return self.hash(code) == code_hash

    def create_signup_verification(
        self,
        identifier: str,
        now: datetime,
    ) -> tuple[OTPVerification, str]:
        code = self.generate()

        verification = OTPVerification(
            identifier=identifier,
            channel=VerificationChannel.EMAIL,
            purpose=VerificationPurpose.SIGNUP,
            code_hash=self.hash(code),
            status=VerificationStatus.PENDING,
            attempt_count=0,
            resend_count=0,
            created_at=now,
            otp_expires_at=now + timedelta(
                minutes=self.OTP_EXPIRY_MINUTES
            ),
            last_sent_at=now,
            session_expires_at=now + timedelta(
                minutes=self.SIGNUP_SESSION_EXPIRY_MINUTES
            ),
        )

        return verification, code

    def refresh_signup_verification(
        self,
        verification: OTPVerification,
        now: datetime,
    ) -> tuple[OTPVerification, str]:
        code = self.generate()

        refreshed_verification = verification.model_copy(
            update={
                "code_hash": self.hash(code),
                "resend_count": verification.resend_count + 1,
                "otp_expires_at": now + timedelta(
                    minutes=self.OTP_EXPIRY_MINUTES
                ),
                "last_sent_at": now,
            }
        )

        return refreshed_verification, code

    def prepare_signup_verification(
        self,
        identifier: str,
        existing_verification: OTPVerification | None,
        now: datetime,
    ) -> tuple[OTPVerification, str] | None:
        if existing_verification is None:
            return self.create_signup_verification(
                identifier=identifier,
                now=now,
            )

        if existing_verification.session_expires_at <= now:
            return self.create_signup_verification(
                identifier=identifier,
                now=now,
            )

        if existing_verification.status == VerificationStatus.LOCKED:
            return None

        cooldown_until = (
            existing_verification.last_sent_at
            + timedelta(seconds=self.RESEND_COOLDOWN_SECONDS)
        )

        if now < cooldown_until:
            return None

        return self.refresh_signup_verification(
            verification=existing_verification,
            now=now,
        )

def get_otp_service() -> OTPService:
    return OTPService()