from datetime import datetime, timezone

from app.models.account import Account, AccountStatus
from app.models.auth import LoginRequest, LoginResponse


def test_account_can_store_password_hash():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash="$2b$12$example-hash",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    assert account.password_hash == "$2b$12$example-hash"


def test_login_request_contains_email_and_password():
    request = LoginRequest(
        email="alice@example.com",
        password="password123",
    )

    assert request.email == "alice@example.com"
    assert request.password == "password123"


def test_login_response_contains_refresh_token():
    response = LoginResponse(
        refresh_token="test-refresh-token",
    )

    assert response.refresh_token == "test-refresh-token"