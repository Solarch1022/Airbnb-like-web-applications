import pytest
from datetime import datetime, timedelta, timezone

from app.models.account import Account, AccountStatus
from app.services.login_service import LoginService
from app.models.auth import (
    Session,
    SessionStatus,
)


class FakeAccountDAO:
    def __init__(
        self,
        account: Account | None,
    ):
        self.account = account
        self.requested_email = None

    def get_account_by_email(
        self,
        email: str,
    ) -> Account | None:
        self.requested_email = email
        return self.account


class FakePasswordService:
    def __init__(
        self,
        verification_result: bool = True,
    ):
        self.verification_result = verification_result
        self.received_password = None
        self.received_password_hash = None

    def verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        self.received_password = password
        self.received_password_hash = password_hash
        return self.verification_result


class FakeSessionDAO:
    def __init__(self):
        self.saved_session = None

    def put_session(self, session):
        self.saved_session = session


class FakeTokenService:
    def __init__(self):
        self.received_account_id = None
        self.received_session_id = None

    def create_refresh_token(
        self,
        account_id: str,
        session_id: str,
    ) -> str:
        self.received_account_id = account_id
        self.received_session_id = session_id
        return "test-refresh-token"


def test_active_account_with_correct_password_can_login():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash="stored-password-hash",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    account_dao = FakeAccountDAO(account)
    session_dao = FakeSessionDAO()
    token_service = FakeTokenService()

    service = LoginService(
        account_dao=account_dao,
        password_service=FakePasswordService(),
        session_dao=session_dao,
        token_service=token_service,
        refresh_token_expiry_days=30,
    )

    refresh_token = service.login(
        email="alice@example.com",
        password="correct-password",
    )

    assert (
        account_dao.requested_email
        == "alice@example.com"
    )

    assert session_dao.saved_session is not None
    assert (
        session_dao.saved_session.account_id
        == "account-001"
    )
    assert (
        session_dao.saved_session.status
        == SessionStatus.ACTIVE
    )

    assert (
        token_service.received_account_id
        == "account-001"
    )
    assert (
        token_service.received_session_id
        == session_dao.saved_session.id
    )

    assert refresh_token == "test-refresh-token"


def test_login_rejects_unknown_email():
    account_dao = FakeAccountDAO(None)

    service = LoginService(
        account_dao=account_dao,
        password_service=FakePasswordService(),
        session_dao=FakeSessionDAO(),
        token_service=FakeTokenService(),
        refresh_token_expiry_days=30,
    )

    with pytest.raises(
        ValueError,
        match="Invalid credentials",
    ):
        service.login(
            email="unknown@example.com",
            password="some-password",
        )


def test_login_rejects_non_active_account():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash="stored-password-hash",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    service = LoginService(
        account_dao=FakeAccountDAO(account),
        password_service=FakePasswordService(),
        session_dao=FakeSessionDAO(),
        token_service=FakeTokenService(),
        refresh_token_expiry_days=30,
    )

    with pytest.raises(
        ValueError,
        match="Invalid credentials",
    ):
        service.login(
            email="alice@example.com",
            password="correct-password",
        )


def test_login_rejects_account_without_password_hash():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash=None,
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    service = LoginService(
        account_dao=FakeAccountDAO(account),
        password_service=FakePasswordService(),
        session_dao=FakeSessionDAO(),
        token_service=FakeTokenService(),
        refresh_token_expiry_days=30,
    )

    with pytest.raises(
        ValueError,
        match="Invalid credentials",
    ):
        service.login(
            email="alice@example.com",
            password="some-password",
        )


def test_login_rejects_incorrect_password():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash="stored-password-hash",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    password_service = FakePasswordService(
        verification_result=False,
    )

    service = LoginService(
        account_dao=FakeAccountDAO(account),
        password_service=password_service,
        session_dao=FakeSessionDAO(),
        token_service=FakeTokenService(),
        refresh_token_expiry_days=30,
    )

    with pytest.raises(
        ValueError,
        match="Invalid credentials",
    ):
        service.login(
            email="alice@example.com",
            password="wrong-password",
        )

    assert (
        password_service.received_password
        == "wrong-password"
    )
    assert (
        password_service.received_password_hash
        == "stored-password-hash"
    )


def test_login_uses_configured_session_expiry():
    now = datetime.now(timezone.utc)

    account = Account(
        id="account-001",
        email="alice@example.com",
        first_name="Alice",
        last_name="Test",
        password_hash="stored-password-hash",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    session_dao = FakeSessionDAO()

    service = LoginService(
        account_dao=FakeAccountDAO(account),
        password_service=FakePasswordService(),
        session_dao=session_dao,
        token_service=FakeTokenService(),
        refresh_token_expiry_days=30,
    )

    service.login(
        email="alice@example.com",
        password="correct-password",
    )

    session = session_dao.saved_session

    assert session is not None
    assert (
        session.expires_at - session.created_at
        == timedelta(days=30)
    )