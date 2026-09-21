import pytest

from datetime import datetime, timedelta, timezone

from app.models.auth import Session, SessionStatus
from app.services.token_service import TokenService
from app.services.refresh_service import RefreshService


TEST_SECRET = (
    "test-secret-key-that-is-at-least-32-bytes-long"
)


class FakeSessionDAO:

    def __init__(self):
        self.sessions = {}

    def get_session(
        self,
        session_id: str,
    ) -> Session | None:
        return self.sessions.get(session_id)


def test_refresh_returns_access_token_for_valid_session():
    session_dao = FakeSessionDAO()

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    session_dao.sessions[session.id] = session

    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=15,
    )

    refresh_token = token_service.create_refresh_token(
        account_id="account-001",
        session_id="session-001",
    )

    service = RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )

    access_token = service.refresh(
        refresh_token=refresh_token
    )

    payload = token_service.verify_access_token(
        access_token
    )

    assert payload["account_id"] == "account-001"
    assert payload["session_id"] == "session-001"
    assert payload["purpose"] == "access"


def test_refresh_rejects_missing_session():
    session_dao = FakeSessionDAO()

    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=15,
    )

    refresh_token = token_service.create_refresh_token(
        account_id="account-001",
        session_id="missing-session",
    )

    service = RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )

    with pytest.raises(
        ValueError,
        match="Session does not exist",
    ):
        service.refresh(
            refresh_token=refresh_token
        )


def test_refresh_rejects_inactive_session():
    session_dao = FakeSessionDAO()

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.EXPIRED,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    session_dao.sessions[session.id] = session

    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=15,
    )

    refresh_token = token_service.create_refresh_token(
        account_id="account-001",
        session_id="session-001",
    )

    service = RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )

    with pytest.raises(
        ValueError,
        match="Session is not active",
    ):
        service.refresh(
            refresh_token=refresh_token
        )


def test_refresh_rejects_account_identity_mismatch():
    session_dao = FakeSessionDAO()

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    session_dao.sessions[session.id] = session

    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=15,
    )

    refresh_token = token_service.create_refresh_token(
        account_id="account-999",
        session_id="session-001",
    )

    service = RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )

    with pytest.raises(
        ValueError,
        match="Session identity does not match",
    ):
        service.refresh(
            refresh_token=refresh_token
        )


def test_refresh_rejects_expired_session():
    session_dao = FakeSessionDAO()

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now - timedelta(days=31),
        expires_at=now - timedelta(minutes=1),
    )

    session_dao.sessions[session.id] = session

    token_service = TokenService(
        secret_key=TEST_SECRET,
        registration_token_expiry_minutes=10,
        refresh_token_expiry_days=30,
        access_token_expiry_minutes=15,
    )

    refresh_token = token_service.create_refresh_token(
        account_id="account-001",
        session_id="session-001",
    )

    service = RefreshService(
        session_dao=session_dao,
        token_service=token_service,
    )

    with pytest.raises(
        ValueError,
        match="Session has expired",
    ):
        service.refresh(
            refresh_token=refresh_token
        )