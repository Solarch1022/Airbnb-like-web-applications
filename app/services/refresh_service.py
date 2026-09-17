from app.models.auth import SessionStatus
from datetime import datetime, timezone

from fastapi import Depends

from app.dao.session_dao import (
    SessionDAO,
    get_session_dao,
)
from app.services.token_service import (
    TokenService,
    get_token_service,
)


class RefreshService:

    def __init__(
        self,
        session_dao: SessionDAO,
        token_service: TokenService,
    ) -> None:
        self._session_dao = session_dao
        self._token_service = token_service

    def refresh(
        self,
        refresh_token: str,
    ) -> str:
        payload = self._token_service.verify_refresh_token(
            refresh_token
        )

        session = self._session_dao.get_session(
            payload["session_id"]
        )

        if session is None:
            raise ValueError(
                "Session does not exist"
            )

        if session.status != SessionStatus.ACTIVE:
            raise ValueError(
                "Session is not active"
            )

        if payload["account_id"] != session.account_id:
            raise ValueError(
                "Session identity does not match"
            )

        if session.expires_at <= datetime.now(timezone.utc):
            raise ValueError(
                "Session has expired"
            )

        return self._token_service.create_access_token(
            account_id=session.account_id,
            session_id=session.id,
        )

def get_refresh_service(
    session_dao: SessionDAO = Depends(
        get_session_dao
    ),
    token_service: TokenService = Depends(
        get_token_service
    ),
) -> RefreshService:
    return RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )