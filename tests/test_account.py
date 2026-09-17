from datetime import datetime, timezone

from app.models.account import Account, AccountStatus


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