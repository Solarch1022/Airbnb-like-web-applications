from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from functools import lru_cache
from app.core.config import Settings, get_settings

class TokenService:

    def __init__(
        self,
        secret_key: str,
        registration_token_expiry_minutes: int = 10,
        refresh_token_expiry_days: int = 30,
        access_token_expiry_minutes: int = 15,
    ) -> None:
        self._secret_key = secret_key
        self._registration_token_expiry_minutes = (
            registration_token_expiry_minutes
        )
        self._refresh_token_expiry_days = (
            refresh_token_expiry_days
        )
        self._access_token_expiry_minutes = (
            access_token_expiry_minutes
        )

    def create_registration_token(
        self,
        account_id: str,
        email: str,
    ) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "account_id": account_id,
            "email": email,
            "purpose": "registration",
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(
                minutes=self._registration_token_expiry_minutes
            ),
        }

        return jwt.encode(
            payload,
            self._secret_key,
            algorithm="HS256",
        )

    def verify_registration_token(
        self,
        token: str,
    ) -> dict:
        payload = jwt.decode(
            token,
            self._secret_key,
            algorithms=["HS256"],
        )

        if payload.get("purpose") != "registration":
            raise jwt.InvalidTokenError(
                "Invalid token purpose"
            )

        return payload

    def create_refresh_token(
        self,
        account_id: str,
        session_id: str,
    ) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "account_id": account_id,
            "session_id": session_id,
            "purpose": "refresh",
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + timedelta(
                days=self._refresh_token_expiry_days
            ),
        }

        return jwt.encode(
            payload,
            self._secret_key,
            algorithm="HS256",
        )

    def verify_refresh_token(
        self,
        token: str,
    ) -> dict:
        payload = jwt.decode(
            token,
            self._secret_key,
            algorithms=["HS256"],
        )

        if payload.get("purpose") != "refresh":
            raise jwt.InvalidTokenError(
                "Invalid token purpose"
            )

        return payload

    def create_access_token(
        self,
        account_id: str,
        session_id: str,
    ) -> str:
        now = datetime.now(timezone.utc)

        payload = {
            "account_id": account_id,
            "session_id": session_id,
            "purpose": "access",
            "iat": now,
            "exp": now + timedelta(
                minutes=self._access_token_expiry_minutes
            ),
        }

        return jwt.encode(
            payload,
            self._secret_key,
            algorithm="HS256",
        )

    def verify_access_token(
        self,
        token: str,
    ) -> dict:
        payload = jwt.decode(
            token,
            self._secret_key,
            algorithms=["HS256"],
        )

        if payload.get("purpose") != "access":
            raise jwt.InvalidTokenError(
                "Invalid token purpose"
            )

        return payload


@lru_cache
def get_token_service() -> TokenService:
    settings: Settings = get_settings()

    return TokenService(
        secret_key=settings.jwt_secret_key,
        registration_token_expiry_minutes=(
            settings.registration_token_expiry_minutes
        ),
        refresh_token_expiry_days=(
            settings.refresh_token_expiry_days
        ),
        access_token_expiry_minutes=(
            settings.access_token_expiry_minutes
        ),
    )