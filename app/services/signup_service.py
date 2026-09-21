from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi import Depends

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.otp_verification_dao import (
    OTPVerificationDAO,
    get_otp_verification_dao,
)
from app.dao.signup_transaction_dao import (
    SignupTransactionDAO,
    get_signup_transaction_dao,
)
from app.models.account import Account, AccountStatus
from app.models.auth import (
    VerificationPurpose,
    VerificationStatus,
    RegistrationToken,
    RegistrationTokenStatus,
)
from app.services.email_service import (
    EmailService,
    get_email_service,
)
from app.services.otp_service import (
    OTPService,
    get_otp_service,
)
from app.services.token_service import (
    TokenService,
    get_token_service,
)
from app.dao.registration_token_dao import (
    RegistrationTokenDAO,
    get_registration_token_dao,
)


class SignupService:

    def __init__(
        self,
        account_dao: AccountDAO,
        verification_dao: OTPVerificationDAO,
        email_service: EmailService,
        otp_service: OTPService,
        transaction_dao: SignupTransactionDAO | None = None,
        token_service: TokenService | None = None,
        registration_token_dao: RegistrationTokenDAO | None = None,
    ) -> None:
        self._account_dao = account_dao
        self._verification_dao = verification_dao
        self._email_service = email_service
        self._otp_service = otp_service
        self._transaction_dao = transaction_dao
        self._token_service = token_service
        self._registration_token_dao = registration_token_dao

    def start_signup(self, email: str) -> None:
        normalized_email = email.strip().lower()

        existing_account = self._account_dao.get_account_by_email(
            normalized_email
        )

        now = datetime.now(timezone.utc)

        if existing_account is None:
            account = Account(
                id=str(uuid4()),
                email=normalized_email,
                status=AccountStatus.UNVERIFIED,
                created_at=now,
                updated_at=now,
            )

            self._account_dao.put_account(account)

        elif existing_account.status != AccountStatus.UNVERIFIED:
            return

        existing_verification = (
            self._verification_dao.get_verification(
                normalized_email,
                VerificationPurpose.SIGNUP,
            )
        )

        prepared = self._otp_service.prepare_signup_verification(
            identifier=normalized_email,
            existing_verification=existing_verification,
            now=now,
        )

        if prepared is None:
            return

        verification, otp = prepared

        self._verification_dao.put_verification(
            verification
        )

        self._email_service.send_verification_code(
            email=normalized_email,
            code=otp,
        )

    def verify_signup_otp(
        self,
        email: str,
        code: str,
    ) -> str | bool:
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

        if now >= verification.otp_expires_at:
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

        if self._transaction_dao is None:
            return False

        try:
            self._transaction_dao.mark_account_pending_setup_and_consume_verification(
                account_id=account.id,
                identifier=normalized_email,
                purpose=VerificationPurpose.SIGNUP,
                code_hash=verification.code_hash,
                updated_at=now,
            )

        except ClientError as exc:
            if (
                exc.response["Error"]["Code"]
                == "TransactionCanceledException"
            ):
                return False

            raise

        if (
            self._token_service is None
            or self._registration_token_dao is None
        ):
            return True

        registration_token = (
            self._token_service.create_registration_token(
                account_id=account.id,
                email=normalized_email,
            )
        )

        payload = (
            self._token_service.verify_registration_token(
                registration_token
            )
        )

        self._registration_token_dao.put_token(
            RegistrationToken(
                jti=payload["jti"],
                account_id=account.id,
                email=normalized_email,
                status=RegistrationTokenStatus.ACTIVE,
                expires_at=datetime.fromtimestamp(
                    payload["exp"],
                    tz=timezone.utc,
                ),
            )
        )

        return registration_token


def get_signup_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    verification_dao: OTPVerificationDAO = Depends(
        get_otp_verification_dao
    ),
    email_service: EmailService = Depends(get_email_service),
    otp_service: OTPService = Depends(get_otp_service),
    registration_token_dao: RegistrationTokenDAO = Depends(
        get_registration_token_dao
    ),
    token_service: TokenService = Depends(get_token_service),
) -> SignupService:
    return SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
        transaction_dao=get_signup_transaction_dao(),
        token_service=token_service,
        registration_token_dao=registration_token_dao,
    )