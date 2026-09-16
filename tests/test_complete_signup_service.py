import pytest
import jwt
from datetime import datetime, timedelta, timezone

from app.services.complete_signup_service import (
    CompleteSignupService,
)
from app.services.token_service import TokenService
from app.models.auth import (
    RegistrationToken,
    RegistrationTokenStatus,
)
from app.models.account import Account, AccountStatus


class FakeAccountDAO:
    def __init__(self):
        self.accounts = {}

    def get_account_by_email(self, email: str):
        return self.accounts.get(email)


class FakeRegistrationTokenDAO:
    def __init__(self):
        self.tokens = {}

    def get_token(self, jti: str):
        return self.tokens.get(jti)


class FakePasswordService:
    def __init__(self):
        self.hashed_password = None

    def hash_password(self, password: str) -> str:
        self.hashed_password = password
        return "hashed-password"

class FakeCompleteSignupTransactionDAO:
    def __init__(self):
        self.complete_signup_call = None

    def complete_signup(
        self,
        account_id: str,
        registration_token_jti: str,
        first_name: str,
        last_name: str,
        password_hash: str,
    ) -> None:
        self.complete_signup_call = {
            "account_id": account_id,
            "registration_token_jti": registration_token_jti,
            "first_name": first_name,
            "last_name": last_name,
            "password_hash": password_hash,
        }

class FailingCompleteSignupTransactionDAO:
    def complete_signup(
        self,
        account_id: str,
        registration_token_jti: str,
        first_name: str,
        last_name: str,
        password_hash: str,
    ) -> None:
        raise RuntimeError("Transaction failed")

def test_complete_signup_rejects_invalid_registration_token():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(jwt.InvalidTokenError):
        service.complete_signup(
            registration_token="not-a-valid-jwt",
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_untracked_registration_token():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_consumed_registration_token():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.CONSUMED,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_registration_token_identity_mismatch():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-999",
            email="attacker@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_missing_account():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_account_not_pending_setup():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_rejects_account_id_mismatch():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-999",
        email="alice@example.com",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=FakePasswordService(),
        complete_signup_transaction_dao=FakeCompleteSignupTransactionDAO()
    )

    with pytest.raises(ValueError):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Test",
            last_name="User",
        )


def test_complete_signup_hashes_password_for_valid_account():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()
    password_service = FakePasswordService()
    transaction_dao = FakeCompleteSignupTransactionDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=password_service,
        complete_signup_transaction_dao=transaction_dao
    )

    service.complete_signup(
        registration_token=registration_token,
        password="SecurePassword123!",
        first_name="Alice",
        last_name="Test",
    )

    assert (
        password_service.hashed_password
        == "SecurePassword123!"
    )


def test_complete_signup_uses_transaction_for_valid_account():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()
    password_service = FakePasswordService()
    transaction_dao = FakeCompleteSignupTransactionDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=password_service,
        complete_signup_transaction_dao=transaction_dao,
    )

    service.complete_signup(
        registration_token=registration_token,
        password="SecurePassword123!",
        first_name="Alice",
        last_name="Test",
    )

    assert transaction_dao.complete_signup_call == {
        "account_id": "account-001",
        "registration_token_jti": payload["jti"],
        "first_name": "Alice",
        "last_name": "Test",
        "password_hash": "hashed-password",
    }


def test_complete_signup_propagates_transaction_failure():
    account_dao = FakeAccountDAO()
    registration_token_dao = FakeRegistrationTokenDAO()
    password_service = FakePasswordService()
    transaction_dao = FailingCompleteSignupTransactionDAO()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    registration_token = (
        token_service.create_registration_token(
            account_id="account-001",
            email="alice@example.com",
        )
    )

    payload = token_service.verify_registration_token(
        registration_token
    )

    registration_token_dao.tokens[payload["jti"]] = (
        RegistrationToken(
            jti=payload["jti"],
            account_id="account-001",
            email="alice@example.com",
            status=RegistrationTokenStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),
        )
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    service = CompleteSignupService(
        account_dao=account_dao,
        registration_token_dao=registration_token_dao,
        token_service=token_service,
        password_service=password_service,
        complete_signup_transaction_dao=transaction_dao,
    )

    with pytest.raises(
        RuntimeError,
        match="Transaction failed",
    ):
        service.complete_signup(
            registration_token=registration_token,
            password="SecurePassword123!",
            first_name="Alice",
            last_name="Test",
        )