import jwt
import pytest

from datetime import datetime, timezone

from app.services.token_service import TokenService

TEST_SECRET = (
    "test-secret-key-that-is-at-least-32-bytes-long"
)

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


def test_create_and_verify_refresh_token():
    service = TokenService(
        secret_key=TEST_SECRET,
        refresh_token_expiry_days=7,
    )

    token = service.create_refresh_token(
        account_id="account-001",
        session_id="session-001",
    )

    payload = service.verify_refresh_token(
        token
    )

    assert payload["account_id"] == "account-001"
    assert payload["session_id"] == "session-001"
    assert payload["purpose"] == "refresh"
    assert "jti" in payload
    assert "iat" in payload
    assert "exp" in payload
    assert (
        payload["exp"] - payload["iat"]
        == 7 * 24 * 60 * 60
    )


def test_verify_refresh_token_rejects_wrong_purpose():
    service = TokenService(
        secret_key=TEST_SECRET,
    )

    registration_token = (
        service.create_registration_token(
            account_id="account-001",
            email="user@example.com",
        )
    )

    with pytest.raises(
        jwt.InvalidTokenError,
        match="Invalid token purpose",
    ):
        service.verify_refresh_token(
            registration_token
        )


def test_create_and_verify_access_token():
    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
    )

    access_token = token_service.create_access_token(
        account_id="account-001",
        session_id="session-001",
    )

    payload = token_service.verify_access_token(
        access_token
    )

    assert payload["account_id"] == "account-001"
    assert payload["session_id"] == "session-001"
    assert payload["purpose"] == "access"
    assert "iat" in payload
    assert "exp" in payload


def test_access_token_uses_configured_expiry():
    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=5,
    )

    access_token = token_service.create_access_token(
        account_id="account-001",
        session_id="session-001",
    )

    payload = token_service.verify_access_token(
        access_token
    )

    assert (
        payload["exp"] - payload["iat"]
        == 5 * 60
    )