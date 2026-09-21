from fastapi import Depends

from app.core.config import Settings, get_settings
from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.session_dao import SessionDAO, get_session_dao
from app.services.password_service import (
    PasswordService,
    get_password_service,
)
from app.services.token_service import (
    TokenService,
    get_token_service,
)

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.account import AccountStatus
from app.models.auth import Session, SessionStatus


class LoginService:

    def __init__(
        self,
        account_dao: AccountDAO,
        password_service: PasswordService,
        session_dao: SessionDAO,
        token_service: TokenService,
        refresh_token_expiry_days: int,
    ) -> None:
        self._account_dao = account_dao
        self._password_service = password_service
        self._session_dao = session_dao
        self._token_service = token_service
        self._refresh_token_expiry_days = (
            refresh_token_expiry_days
        )

    def login(
        self,
        email: str,
        password: str,
    ) -> str:
        account = self._account_dao.get_account_by_email(
            email
        )

        if account is None:
            raise ValueError("Invalid credentials")

        if account.status != AccountStatus.ACTIVE:
            raise ValueError("Invalid credentials")

        if account.password_hash is None:
            raise ValueError("Invalid credentials")

        password_is_valid = (
            self._password_service.verify_password(
                password,
                account.password_hash,
            )
        )

        if not password_is_valid:
            raise ValueError("Invalid credentials")

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

        self._session_dao.put_session(session)

        refresh_token = (
            self._token_service.create_refresh_token(
                account_id=account.id,
                session_id=session.id,
            )
        )

        return refresh_token


def get_login_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    password_service: PasswordService = Depends(
        get_password_service
    ),
    session_dao: SessionDAO = Depends(get_session_dao),
    token_service: TokenService = Depends(
        get_token_service
    ),
    settings: Settings = Depends(get_settings),
) -> LoginService:
    return LoginService(
        account_dao=account_dao,
        password_service=password_service,
        session_dao=session_dao,
        token_service=token_service,
        refresh_token_expiry_days=(
            settings.refresh_token_expiry_days
        ),
    )
