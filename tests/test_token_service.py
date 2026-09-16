import jwt
import pytest

from datetime import datetime, timezone

from app.services.token_service import TokenService


def test_create_and_verify_registration_token():
    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    token = token_service.create_registration_token(
        account_id="account-123",
        email="user@example.com",
    )

    payload = token_service.verify_registration_token(token)

    assert payload["account_id"] == "account-123"
    assert payload["email"] == "user@example.com"
    assert payload["purpose"] == "registration"
    assert "exp" in payload
    assert "jti" in payload


def test_verify_registration_token_rejects_wrong_purpose():
    secret_key = "test-secret-key-at-least-32-bytes-long"

    token_service = TokenService(
        secret_key=secret_key,
        registration_token_expiry_minutes=10,
    )

    token = jwt.encode(
        {
            "account_id": "account-123",
            "email": "user@example.com",
            "purpose": "access",
            "jti": "test-jti",
            "exp": datetime.now(timezone.utc).timestamp() + 600,
        },
        secret_key,
        algorithm="HS256",
    )

    with pytest.raises(jwt.InvalidTokenError):
        token_service.verify_registration_token(token)
