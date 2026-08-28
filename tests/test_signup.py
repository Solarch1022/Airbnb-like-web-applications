import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone

from app.main import create_app
from app.models.account import Account, AccountStatus
from app.models.auth import OTPVerification, VerificationStatus
from app.services.otp_service import OTPService
from app.services.signup_service import SignupService


class FakeAccountDAO:
    def __init__(self):
        self.accounts = {}

    def get_account_by_email(self, email: str):
        return self.accounts.get(email)

    def put_account(self, account: Account):
        self.accounts[str(account.email).lower()] = account
        return account

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

class FakeEmailService:
    def __init__(self):
        self.sent_email = None
        self.sent_code = None

    def send_verification_code(self, email, code):
        self.sent_email = email
        self.sent_code = code

class FakeEmailService:
    def __init__(self):
        self.sent_email = None
        self.sent_code = None

    def send_verification_code(self, email, code):
        self.sent_email = email
        self.sent_code = code


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

    expires_at = stored.expires_at

    min_expected = before.timestamp() + 600
    max_expected = after.timestamp() + 600

    assert min_expected <= expires_at.timestamp() <= max_expected

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
        expires_at=now - timedelta(minutes=1),
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
        expires_at=now,
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
        expires_at=now,
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