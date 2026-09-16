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
    ) -> None:
        self._secret_key = secret_key
        self._registration_token_expiry_minutes = (
            registration_token_expiry_minutes
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


@lru_cache
def get_token_service() -> TokenService:
    settings: Settings = get_settings()

    return TokenService(
        secret_key=settings.jwt_secret_key,
        registration_token_expiry_minutes=(
            settings.registration_token_expiry_minutes
        ),
    )