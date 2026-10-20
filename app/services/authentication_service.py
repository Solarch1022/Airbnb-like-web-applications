from datetime import datetime, timezone

from fastapi import Depends

from app.dao.account_dao import AccountDAO, get_account_dao
from app.dao.session_dao import SessionDAO, get_session_dao
from app.models.account import AccountStatus
from app.models.auth import CurrentUser, SessionStatus
from app.services.token_service import TokenService, get_token_service


class AuthenticationError(ValueError):
    pass


class AuthenticationService:

    def __init__(
        self,
        account_dao: AccountDAO,
        session_dao: SessionDAO,
        token_service: TokenService,
    ) -> None:
        self._account_dao = account_dao
        self._session_dao = session_dao
        self._token_service = token_service

    def authenticate(
        self,
        access_token: str,
    ) -> CurrentUser:
        payload = self._token_service.verify_access_token(
            access_token
        )
        session = self._session_dao.get_session(
            payload["session_id"]
        )

        if (
            session is None
            or session.status != SessionStatus.ACTIVE
            or session.expires_at.tzinfo is None
            or session.expires_at <= datetime.now(timezone.utc)
            or session.account_id != payload["account_id"]
        ):
            raise AuthenticationError("Invalid session")

        account = self._account_dao.get_account(
            session.account_id
        )

        if (
            account is None
            or account.status != AccountStatus.ACTIVE
            or account.id != session.account_id
        ):
            raise AuthenticationError("Invalid account")

        return CurrentUser(
            account_id=account.id,
            session_id=session.id,
        )


def get_authentication_service(
    account_dao: AccountDAO = Depends(get_account_dao),
    session_dao: SessionDAO = Depends(get_session_dao),
    token_service: TokenService = Depends(get_token_service),
) -> AuthenticationService:
    return AuthenticationService(
        account_dao=account_dao,
        session_dao=session_dao,
        token_service=token_service,
    )
