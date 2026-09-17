from datetime import datetime, timedelta, timezone

from app.models.auth import Session, SessionStatus


def test_session_stores_authentication_session_data():
    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    assert session.id == "session-001"
    assert session.account_id == "account-001"
    assert session.status == SessionStatus.ACTIVE
    assert session.created_at == now
    assert session.expires_at == now + timedelta(days=30)