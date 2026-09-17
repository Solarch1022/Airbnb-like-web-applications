import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError

from app.dao import account_dao
from app.main import create_app
from app.routers.auth import router
from app.models.account import Account, AccountStatus
from app.models.auth import (
    OTPVerification,
    VerificationStatus,
    VerificationPurpose,
    RegistrationToken,
    RegistrationTokenStatus,
    CompleteSignupRequest,
    CompleteSignupResponse,
)
from app.services.token_service import TokenService
from app.services.otp_service import OTPService
from app.services.signup_service import (
    SignupService,
    get_signup_service,
)
from app.services.complete_signup_service import (
    get_complete_signup_service,
)



class FakeAccountDAO:
    def __init__(self):
        self.accounts = {}

    def get_account_by_email(self, email: str):
        return self.accounts.get(email)

    def put_account(self, account: Account):
        self.accounts[str(account.email).lower()] = account
        return account

class FakeSignupTransactionDAO:
    def __init__(
        self,
        account_dao,
        verification_dao,
    ):
        self._account_dao = account_dao
        self._verification_dao = verification_dao
        self.calls = []

    def mark_account_pending_setup_and_consume_verification(
        self,
        account_id: str,
        identifier: str,
        purpose,
        code_hash: str,
        updated_at,
    ) -> None:
        self.calls.append(
            {
                "account_id": account_id,
                "identifier": identifier,
                "purpose": purpose,
                "code_hash": code_hash,
                "updated_at": updated_at,
            }
        )

        account = self._account_dao.get_account_by_email(identifier)

        updated_account = account.model_copy(
            update={
                "status": AccountStatus.PENDING_SETUP,
                "updated_at": updated_at,
            }
        )

        self._account_dao.put_account(updated_account)

        verification = self._verification_dao.get_verification(
            identifier,
            purpose,
        )

        consumed_verification = verification.model_copy(
            update={
                "status": VerificationStatus.CONSUMED,
            }
        )

        self._verification_dao.update_verification(
            consumed_verification
        )

class FailingSignupTransactionDAO:
    def mark_account_pending_setup_and_consume_verification(
        self,
        account_id: str,
        identifier: str,
        purpose,
        code_hash: str,
        updated_at,
    ) -> None:
        raise ClientError(
            {
                "Error": {
                    "Code": "TransactionCanceledException",
                    "Message": "Transaction cancelled",
                }
            },
            "TransactWriteItems",
        )

class UnexpectedFailingSignupTransactionDAO:
    def mark_account_pending_setup_and_consume_verification(
        self,
        account_id: str,
        identifier: str,
        purpose,
        code_hash: str,
        updated_at,
    ) -> None:
        raise ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Table not found",
                }
            },
            "TransactWriteItems",
        )

class FakeVerificationDAO:
    def __init__(self):
        self.verifications: dict[
            tuple[str, str],
            OTPVerification,
        ] = {}

    def get_verification(
        self,
        identifier: str,
        purpose,
    ):
        key = (
            identifier,
            purpose.value,
        )

        return self.verifications.get(key)

    def put_verification(
        self,
        verification: OTPVerification,
    ) -> OTPVerification:
        key = (
            verification.identifier,
            verification.purpose.value,
        )

        self.verifications[key] = verification
        return verification

    def update_verification(
        self,
        verification: OTPVerification,
    ) -> OTPVerification:
        return self.put_verification(verification)

    def record_failed_attempt(
        self,
        identifier: str,
        purpose,
    ) -> OTPVerification:
        key = (
            identifier,
            purpose.value,
        )

        verification = self.verifications[key]

        new_attempt_count = verification.attempt_count + 1

        new_status = (
            VerificationStatus.LOCKED
            if new_attempt_count >= 3
            else VerificationStatus.PENDING
        )

        updated = verification.model_copy(
            update={
                "attempt_count": new_attempt_count,
                "status": new_status,
            }
        )

        self.verifications[key] = updated
        return updated

class FakeEmailService:
    def __init__(self):
        self.sent_email = None
        self.sent_code = None
        self.sent = []

    def send_verification_code(
        self,
        email: str,
        code: str,
    ) -> None:
        self.sent_email = email
        self.sent_code = code

        self.sent.append(
            {
                "email": email,
                "code": code,
            }
        )

class FakeRegistrationTokenDAO:
    def __init__(self):
        self.tokens: dict[str, RegistrationToken] = {}

    def put_token(
        self,
        token: RegistrationToken,
    ) -> RegistrationToken:
        self.tokens[token.jti] = token
        return token

    def get_token(
        self,
        jti: str,
    ) -> RegistrationToken | None:
        return self.tokens.get(jti)

def test_start_signup_with_new_email():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    account = account_dao.accounts["alice@example.com"]

    assert account.status == AccountStatus.UNVERIFIED
    assert email_service.sent_email == "alice@example.com"
    assert email_service.sent_code is not None
    assert ("alice@example.com", "signup",) in verification_dao.verifications

def test_start_signup_with_active_account_does_not_send_signup_otp():
    account_dao = FakeAccountDAO()
    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    assert verification_dao.verifications == {}
    assert email_service.sent_email is None
    assert email_service.sent_code is None

def test_start_signup_normalizes_email():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup(" Alice@Example.com ")

    assert email_service.sent_email == "alice@example.com"
    assert ("alice@example.com", "signup",) in verification_dao.verifications

def test_existing_account_check_is_case_insensitive():
    account_dao = FakeAccountDAO()
    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup(" Alice@Example.com ")

    assert len(account_dao.accounts) == 1

def test_signup_generates_secure_otp():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    otp = email_service.sent_code
    stored = verification_dao.verifications[("alice@example.com", "signup")]

    # OTP should be exactly 6 digits
    assert otp is not None
    assert len(otp) == 6
    assert otp.isdigit()

    # Plain OTP must not be stored
    assert stored.code_hash != otp

    # SHA-256 hash should contain 64 hexadecimal characters
    assert len(stored.code_hash) == 64

def test_signup_otp_expires_in_ten_minutes():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    before = datetime.now(timezone.utc)

    service.start_signup("alice@example.com")

    after = datetime.now(timezone.utc)

    stored = verification_dao.verifications[("alice@example.com", "signup")]

    otp_expires_at = stored.otp_expires_at

    min_expected = before.timestamp() + 600
    max_expected = after.timestamp() + 600

    assert min_expected <= otp_expires_at.timestamp() <= max_expected

def test_signup_endpoint_rejects_invalid_email():

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 422

def test_unverified_account_resend_preserves_attempt_count():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash="old-hash",
        status="pending",
        attempt_count=2,
        resend_count=1,
        created_at=now,
        otp_expires_at=now - timedelta(minutes=1),
        last_sent_at=now - timedelta(minutes=2),
        session_expires_at=now + timedelta(minutes=30),
        )

    verification_dao.put_verification(
        existing_verification
    )

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert stored.attempt_count == 2
    assert stored.resend_count == 2
    assert stored.code_hash != "old-hash"
    assert email_service.sent_email == "alice@example.com"
    assert email_service.sent_code is not None

def test_unverified_account_does_not_resend_during_cooldown():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash="old-hash",
        status="pending",
        attempt_count=1,
        resend_count=1,
        created_at=now,
        otp_expires_at=now,
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(existing_verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert stored.resend_count == 1
    assert stored.code_hash == "old-hash"
    assert email_service.sent_email is None
    assert email_service.sent_code is None

def test_locked_signup_session_does_not_resend_otp():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash="old-hash",
        status="locked",
        attempt_count=3,
        resend_count=1,
        created_at=now,
        otp_expires_at=now,
        last_sent_at=now - timedelta(minutes=5),
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(existing_verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=OTPService(),
    )

    service.start_signup("alice@example.com")

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert stored.status == VerificationStatus.LOCKED
    assert stored.attempt_count == 3
    assert stored.code_hash == "old-hash"
    assert email_service.sent_email is None
    assert email_service.sent_code is None

def test_verify_signup_otp_marks_account_pending_setup_and_consumes_verification():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status="pending",
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    transaction_dao = FakeSignupTransactionDAO(
        account_dao=account_dao,
        verification_dao=verification_dao,
    )

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
        transaction_dao=transaction_dao,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    account = account_dao.accounts["alice@example.com"]
    stored_verification = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert result is True
    assert account.status == AccountStatus.PENDING_SETUP
    assert stored_verification.status == VerificationStatus.CONSUMED

    assert len(transaction_dao.calls) == 1

    call = transaction_dao.calls[0]

    assert call["account_id"] == "account-001"
    assert call["identifier"] == "alice@example.com"
    assert call["purpose"] == VerificationPurpose.SIGNUP
    assert call["code_hash"] == verification.code_hash

def test_verify_signup_otp_records_first_failed_attempt():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash("123456"),
        status="pending",
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code="654321",
    )

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    account = account_dao.accounts["alice@example.com"]

    assert result is False
    assert stored.attempt_count == 1
    assert stored.status == VerificationStatus.PENDING
    assert account.status == AccountStatus.UNVERIFIED

def test_verify_signup_otp_locks_after_three_failed_attempts():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash("123456"),
        status="pending",
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    first_result = service.verify_signup_otp(
        email="alice@example.com",
        code="000001",
    )

    second_result = service.verify_signup_otp(
        email="alice@example.com",
        code="000002",
    )

    third_result = service.verify_signup_otp(
        email="alice@example.com",
        code="000003",
    )

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    account = account_dao.accounts["alice@example.com"]

    assert first_result is False
    assert second_result is False
    assert third_result is False

    assert stored.attempt_count == 3
    assert stored.status == VerificationStatus.LOCKED
    assert account.status == AccountStatus.UNVERIFIED

def test_locked_signup_verification_rejects_correct_otp():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.LOCKED,
        attempt_count=3,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    account = account_dao.accounts["alice@example.com"]

    assert result is False
    assert stored.status == VerificationStatus.LOCKED
    assert stored.attempt_count == 3
    assert account.status == AccountStatus.UNVERIFIED

def test_expired_signup_otp_is_rejected():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.PENDING,
        attempt_count=0,
        resend_count=0,
        created_at=now - timedelta(minutes=20),
        otp_expires_at=now - timedelta(minutes=1),
        last_sent_at=now - timedelta(minutes=20),
        session_expires_at=now + timedelta(minutes=40),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    account = account_dao.accounts["alice@example.com"]
    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert result is False
    assert account.status == AccountStatus.UNVERIFIED
    assert stored.status == VerificationStatus.PENDING
    assert stored.attempt_count == 0

def test_consumed_signup_otp_cannot_be_replayed():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.PENDING_SETUP,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.CONSUMED,
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert result is False
    assert stored.status == VerificationStatus.CONSUMED
    assert stored.attempt_count == 0

def test_expired_locked_signup_session_starts_new_session():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
    )

    old_verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash("111111"),
        status=VerificationStatus.LOCKED,
        attempt_count=3,
        resend_count=2,
        created_at=now - timedelta(hours=2),
        otp_expires_at=now - timedelta(hours=1, minutes=50),
        last_sent_at=now - timedelta(hours=2),
        session_expires_at=now - timedelta(hours=1),
    )

    verification_dao.put_verification(old_verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    service.start_signup("alice@example.com")

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert len(email_service.sent) == 1
    assert stored.status == VerificationStatus.PENDING
    assert stored.attempt_count == 0
    assert stored.resend_count == 0
    assert stored.created_at > old_verification.created_at
    assert stored.session_expires_at > now

def test_expired_pending_signup_session_starts_new_session():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
    )

    old_verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash("111111"),
        status=VerificationStatus.PENDING,
        attempt_count=2,
        resend_count=3,
        created_at=now - timedelta(hours=2),
        otp_expires_at=now - timedelta(hours=1, minutes=50),
        last_sent_at=now - timedelta(hours=2),
        session_expires_at=now - timedelta(hours=1),
    )

    verification_dao.put_verification(old_verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
    )

    service.start_signup("alice@example.com")

    stored = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert len(email_service.sent) == 1
    assert stored.status == VerificationStatus.PENDING
    assert stored.attempt_count == 0
    assert stored.resend_count == 0
    assert stored.created_at > old_verification.created_at
    assert stored.session_expires_at > now

def test_verify_signup_otp_returns_false_when_transaction_conflicts():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.PENDING,
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
        transaction_dao=FailingSignupTransactionDAO(),
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    assert result is False

def test_verify_signup_otp_reraises_unexpected_transaction_error():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.PENDING,
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
        transaction_dao=UnexpectedFailingSignupTransactionDAO(),
    )

    with pytest.raises(ClientError) as exc_info:
        service.verify_signup_otp(
            email="alice@example.com",
            code=otp,
        )

    assert (
        exc_info.value.response["Error"]["Code"]
        == "ResourceNotFoundException"
    )


def test_verify_signup_otp_returns_registration_token():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    registration_token_dao = FakeRegistrationTokenDAO()
    email_service = FakeEmailService()
    otp_service = OTPService()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    now = datetime.now(timezone.utc)

    account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status="pending",
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    verification_dao.put_verification(verification)

    transaction_dao = FakeSignupTransactionDAO(
        account_dao=account_dao,
        verification_dao=verification_dao,
    )

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
        otp_service=otp_service,
        transaction_dao=transaction_dao,
        token_service=token_service,
        registration_token_dao=registration_token_dao,
    )

    result = service.verify_signup_otp(
        email="alice@example.com",
        code=otp,
    )

    assert isinstance(result, str)

    payload = token_service.verify_registration_token(result)

    assert payload["account_id"] == "account-001"
    assert payload["email"] == "alice@example.com"
    assert payload["purpose"] == "registration"

    stored_token = registration_token_dao.get_token(
        payload["jti"]
    )

    assert stored_token is not None
    assert stored_token.account_id == "account-001"
    assert stored_token.email == "alice@example.com"
    assert stored_token.status == RegistrationTokenStatus.ACTIVE


def test_verify_signup_endpoint_returns_registration_token():
    app = create_app()
    client = TestClient(app)

    fake_account_dao = FakeAccountDAO()
    fake_verification_dao = FakeVerificationDAO()
    fake_email_service = FakeEmailService()
    fake_registration_token_dao = FakeRegistrationTokenDAO()

    otp_service = OTPService()

    token_service = TokenService(
        secret_key="test-secret-key-at-least-32-bytes-long",
        registration_token_expiry_minutes=10,
    )

    now = datetime.now(timezone.utc)

    fake_account_dao.accounts["alice@example.com"] = Account(
        id="account-001",
        email="alice@example.com",
        status=AccountStatus.UNVERIFIED,
        created_at=now,
        updated_at=now,
    )

    otp = "123456"

    verification = OTPVerification(
        identifier="alice@example.com",
        channel="email",
        purpose="signup",
        code_hash=otp_service.hash(otp),
        status=VerificationStatus.PENDING,
        attempt_count=0,
        resend_count=0,
        created_at=now,
        otp_expires_at=now + timedelta(minutes=10),
        last_sent_at=now,
        session_expires_at=now + timedelta(minutes=60),
    )

    fake_verification_dao.put_verification(verification)

    transaction_dao = FakeSignupTransactionDAO(
        account_dao=fake_account_dao,
        verification_dao=fake_verification_dao,
    )

    service = SignupService(
        account_dao=fake_account_dao,
        verification_dao=fake_verification_dao,
        email_service=fake_email_service,
        otp_service=otp_service,
        transaction_dao=transaction_dao,
        token_service=token_service,
        registration_token_dao=fake_registration_token_dao,
    )

    app.dependency_overrides[get_signup_service] = (
        lambda: service
    )

    response = client.post(
        "/auth/verify",
        json={
            "email": "alice@example.com",
            "code": otp,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["message"] == "Account verified"
    assert isinstance(
        body["registration_token"],
        str,
    )
    assert body["registration_token"]


def test_complete_signup_request_does_not_require_email():
    request = CompleteSignupRequest(
        registration_token="test-registration-token",
        password="SecurePassword123!",
        first_name="Test",
        last_name="User",
    )

    assert request.registration_token == "test-registration-token"
    assert request.password == "SecurePassword123!"
    assert request.first_name == "Test"
    assert request.last_name == "User"


def test_complete_signup_response_contains_refresh_token():
    response = CompleteSignupResponse(
        message="Signup completed",
        refresh_token="test-refresh-token",
    )

    assert response.message == "Signup completed"
    assert response.refresh_token == "test-refresh-token"


def test_complete_signup_endpoint_returns_refresh_token():
    class FakeCompleteSignupService:
        def complete_signup(
            self,
            registration_token: str,
            password: str,
            first_name: str,
            last_name: str,
        ):
            assert registration_token == "test-registration-token"
            assert password == "SecurePassword123!"
            assert first_name == "Test"
            assert last_name == "User"

            return "test-refresh-token"

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_complete_signup_service] = (
        lambda: FakeCompleteSignupService()
    )

    client = TestClient(app)

    response = client.post(
        "/auth/complete-signup",
        json={
            "registration_token": "test-registration-token",
            "password": "SecurePassword123!",
            "first_name": "Test",
            "last_name": "User",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Signup completed",
        "refresh_token": "test-refresh-token",
    }