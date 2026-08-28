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

def test_verify_signup_otp_activates_account_and_consumes_verification():
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
        expires_at=now + timedelta(minutes=10),
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

    account = account_dao.accounts["alice@example.com"]
    stored_verification = verification_dao.verifications[
        ("alice@example.com", "signup")
    ]

    assert result is True
    assert account.status == AccountStatus.ACTIVE
    assert stored_verification.status == VerificationStatus.CONSUMED

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
        expires_at=now + timedelta(minutes=10),
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
        expires_at=now + timedelta(minutes=10),
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
        expires_at=now + timedelta(minutes=10),
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
        expires_at=now - timedelta(minutes=1),
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
        status=AccountStatus.ACTIVE,
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
        expires_at=now + timedelta(minutes=10),
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
        expires_at=now - timedelta(hours=1, minutes=50),
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
        expires_at=now - timedelta(hours=1, minutes=50),
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