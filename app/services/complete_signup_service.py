from fastapi import Depends
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.auth import Session, SessionStatus

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.registration_token_dao import (
    RegistrationTokenDAO,
    get_registration_token_dao,
)
from app.dao.complete_signup_transaction_dao import (
    CompleteSignupTransactionDAO,
    get_complete_signup_transaction_dao,
)
from app.services.token_service import (
    TokenService,
    get_token_service,
)
from app.services.password_service import (
    PasswordService,
    get_password_service,
)
from app.models.auth import RegistrationTokenStatus
from app.models.account import AccountStatus
from app.core.config import Settings, get_settings


class CompleteSignupService:

    def __init__(
        self,
        account_dao: AccountDAO,
        registration_token_dao: RegistrationTokenDAO,
        token_service: TokenService,
        password_service: PasswordService,
        complete_signup_transaction_dao:
            CompleteSignupTransactionDAO,
        refresh_token_expiry_days: int = 30,
    ) -> None:
        self._account_dao = account_dao
        self._registration_token_dao = registration_token_dao
        self._token_service = token_service
        self._password_service = password_service
        self._complete_signup_transaction_dao = (
            complete_signup_transaction_dao
        )
        self._refresh_token_expiry_days = (
            refresh_token_expiry_days
        )

    def complete_signup(
        self,
        registration_token: str,
        password: str,
        first_name: str,
        last_name: str,
    ) -> str:
        payload = self._token_service.verify_registration_token(
            registration_token
        )

        stored_token = self._registration_token_dao.get_token(
            payload["jti"]
        )

        if stored_token is None:
            raise ValueError(
                "Registration token is not recognized"
            )

        if stored_token.status != RegistrationTokenStatus.ACTIVE:
            raise ValueError(
                "Registration token is not active"
            )

        if (
            stored_token.account_id != payload["account_id"]
            or str(stored_token.email).lower()
            != payload["email"].lower()
        ):
            raise ValueError(
                "Registration token identity does not match"
            )

        account = self._account_dao.get_account_by_email(
            payload["email"]
        )

        if account is None:
            raise ValueError(
                "Account does not exist"
            )

        if account.status != AccountStatus.PENDING_SETUP:
            raise ValueError(
                "Account is not pending setup"
            )

        if account.id != payload["account_id"]:
            raise ValueError(
                "Account identity does not match"
            )

        password_hash = self._password_service.hash_password(
            password
        )

        now = datetime.now(timezone.utc)

        session = Session(
            id=str(uuid4()),
            account_id=account.id,
            status=SessionStatus.ACTIVE,
            created_at=now,
            expires_at=now + timedelta(
                days=self._refresh_token_expiry_days
            ),
        )

        refresh_token = self._token_service.create_refresh_token(
            account_id=account.id,
            session_id=session.id,
        )

        self._complete_signup_transaction_dao.complete_signup(
            account_id=account.id,
            registration_token_jti=payload["jti"],
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            session=session,
        )

        return refresh_token

def get_complete_signup_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    registration_token_dao: RegistrationTokenDAO = Depends(
        get_registration_token_dao
    ),
    token_service: TokenService = Depends(get_token_service),
    password_service: PasswordService = Depends(
        get_password_service
    ),
    complete_signup_transaction_dao: CompleteSignupTransactionDAO = Depends(
        get_complete_signup_transaction_dao
    ),
    settings: Settings = Depends(get_settings),
) -> CompleteSignupService:
    return CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=password_service,
        complete_signup_transaction_dao=(
            complete_signup_transaction_dao
        ),
        refresh_token_expiry_days=(
            settings.refresh_token_expiry_days
        ),
    )
