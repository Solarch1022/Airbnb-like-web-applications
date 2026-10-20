from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.account import Account, AccountStatus
from app.models.auth import CurrentUser, Session, SessionStatus
from app.routers.auth import router
from app.services.authentication_service import (
    AuthenticationError,
    AuthenticationService,
    get_authentication_service,
)
from app.services.token_service import TokenService


TEST_SECRET = "test-secret-key-that-is-at-least-32-bytes-long"


class FakeAccountDAO:
    def __init__(self, account):
        self.account = account

    def get_account(self, account_id):
        assert account_id == "account-001"
        return self.account


class FakeSessionDAO:
    def __init__(self, session):
        self.session = session

    def get_session(self, session_id):
        assert session_id == "session-001"
        return self.session


@pytest.fixture
def auth_context():
    now = datetime.now(timezone.utc)
    account_dao = FakeAccountDAO(Account(
        id="account-001",
        email="alice@example.com",
        password_hash="private-password-hash",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    ))
    session_dao = FakeSessionDAO(Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=1),
    ))
    token_service = TokenService(secret_key=TEST_SECRET)
    service = AuthenticationService(
        account_dao=account_dao,
        session_dao=session_dao,
        token_service=token_service,
    )
    token = token_service.create_access_token(
        account_id="account-001",
        session_id="session-001",
    )
    return service, account_dao, session_dao, token_service, token


def test_authenticate_returns_typed_identity(auth_context):
    service, _, _, _, token = auth_context
    assert service.authenticate(token) == CurrentUser(
        account_id="account-001",
        session_id="session-001",
    )


@pytest.mark.parametrize("failure", [
    "missing_session", "expired_session", "inactive_session",
    "wrong_account", "missing_account", "inactive_account",
])
def test_authenticate_rejects_invalid_state(auth_context, failure):
    service, accounts, sessions, _, token = auth_context
    if failure == "missing_session":
        sessions.session = None
    elif failure == "expired_session":
        sessions.session.expires_at = datetime.now(timezone.utc)
    elif failure == "inactive_session":
        sessions.session.status = SessionStatus.EXPIRED
    elif failure == "wrong_account":
        sessions.session.account_id = "another-account"
    elif failure == "missing_account":
        accounts.account = None
    else:
        accounts.account.status = AccountStatus.DEACTIVATED
    with pytest.raises(AuthenticationError):
        service.authenticate(token)


@pytest.mark.parametrize("field", [
    "account_id", "session_id", "purpose", "iat", "exp",
])
def test_access_token_requires_claims(auth_context, field):
    _, _, _, tokens, token = auth_context
    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
    del payload[field]
    invalid = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify_access_token(invalid)


@pytest.mark.parametrize("field,value", [
    ("account_id", ""), ("session_id", " "),
    ("account_id", 123), ("session_id", []),
    ("iat", "123"), ("exp", True),
])
def test_access_token_rejects_invalid_claim_types(auth_context, field, value):
    _, _, _, tokens, token = auth_context
    payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
    payload[field] = value
    invalid = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        tokens.verify_access_token(invalid)


@pytest.fixture
def auth_client(auth_context):
    service, _, _, _, _ = auth_context
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_authentication_service] = lambda: service
    return TestClient(app)


def test_me_returns_identity_without_account_secrets(auth_context, auth_client):
    token = auth_context[4]
    response = auth_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "account_id": "account-001", "session_id": "session-001",
    }


@pytest.mark.parametrize("kind", [
    "missing", "basic", "malformed", "expired", "signature",
    "refresh", "registration", "session", "account",
])
def test_me_returns_401_for_invalid_authentication(auth_context, auth_client, kind):
    _, accounts, sessions, tokens, token = auth_context
    if kind == "missing":
        headers = {}
    elif kind == "basic":
        headers = {"Authorization": "Basic abc"}
    else:
        if kind == "malformed":
            token = "not-a-jwt"
        elif kind in ("expired", "signature"):
            payload = jwt.decode(token, TEST_SECRET, algorithms=["HS256"])
            if kind == "expired":
                payload["iat"] -= 2000
                payload["exp"] = payload["iat"] + 100
            secret = TEST_SECRET if kind == "expired" else TEST_SECRET + "wrong"
            token = jwt.encode(payload, secret, algorithm="HS256")
        elif kind == "refresh":
            token = tokens.create_refresh_token("account-001", "session-001")
        elif kind == "registration":
            token = tokens.create_registration_token("account-001", "alice@example.com")
        elif kind == "session":
            sessions.session = None
        elif kind == "account":
            accounts.account.status = AccountStatus.DEACTIVATED
        headers = {"Authorization": f"Bearer {token}"}
    response = auth_client.get("/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_public_auth_route_does_not_require_bearer(auth_client):
    response = auth_client.post("/auth/login", json={"email": "invalid"})
    assert response.status_code == 422
