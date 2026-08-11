import pytest
from fastapi import HTTPException
from app.services.signup_service import SignupService
from datetime import datetime, timezone
from fastapi.testclient import TestClient


class FakeAccountDAO:
    def __init__(self):
        self.accounts = {}

    def get_account_by_email(self, email):
        return self.accounts.get(email)


class FakeVerificationDAO:
    def __init__(self):
        self.verifications = {}

    def put_verification(self, verification):
        self.verifications[verification["email"]] = verification
        return verification


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
    )

    service.start_signup("alice@example.com")

    assert email_service.sent_email == "alice@example.com"
    assert email_service.sent_code is not None
    assert "alice@example.com" in verification_dao.verifications

def test_start_signup_with_duplicate_email():
    account_dao = FakeAccountDAO()
    account_dao.accounts["alice@example.com"] = {
        "id": "account-001",
        "email": "alice@example.com",
    }

    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.start_signup("alice@example.com")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Email is already registered"

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
    )

    service.start_signup(" Alice@Example.com ")

    assert email_service.sent_email == "alice@example.com"
    assert "alice@example.com" in verification_dao.verifications

def test_duplicate_email_check_is_case_insensitive():
    account_dao = FakeAccountDAO()
    account_dao.accounts["alice@example.com"] = {
        "id": "account-001",
        "email": "alice@example.com",
    }

    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
    )

    with pytest.raises(HTTPException) as exc_info:
        service.start_signup(" Alice@Example.com ")

    assert exc_info.value.status_code == 409
    assert verification_dao.verifications == {}
    assert email_service.sent_email is None

def test_signup_generates_secure_otp():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
    )

    service.start_signup("alice@example.com")

    otp = email_service.sent_code
    stored = verification_dao.verifications["alice@example.com"]

    # OTP should be exactly 6 digits
    assert otp is not None
    assert len(otp) == 6
    assert otp.isdigit()

    # Plain OTP must not be stored
    assert stored["code_hash"] != otp

    # SHA-256 hash should contain 64 hexadecimal characters
    assert len(stored["code_hash"]) == 64

def test_signup_otp_expires_in_ten_minutes():
    account_dao = FakeAccountDAO()
    verification_dao = FakeVerificationDAO()
    email_service = FakeEmailService()

    service = SignupService(
        account_dao=account_dao,
        verification_dao=verification_dao,
        email_service=email_service,
    )

    before = datetime.now(timezone.utc)

    service.start_signup("alice@example.com")

    after = datetime.now(timezone.utc)

    stored = verification_dao.verifications["alice@example.com"]

    expires_at = stored["expires_at"]

    min_expected = before.timestamp() + 600
    max_expected = after.timestamp() + 600

    assert min_expected <= expires_at.timestamp() <= max_expected

def test_signup_endpoint_rejects_invalid_email():
    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "not-an-email"},
    )

    assert response.status_code == 422