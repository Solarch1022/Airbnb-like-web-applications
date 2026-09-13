from datetime import datetime, timedelta, timezone

from app.models.auth import (
    OTPVerification,
    VerificationChannel,
    VerificationPurpose,
    VerificationStatus,
)

from app.services.otp_service import OTPService


def test_generate_returns_six_digit_code():
    service = OTPService()

    code = service.generate()

    assert len(code) == 6
    assert code.isdigit()


def test_hash_returns_sha256_hash():
    service = OTPService()

    code_hash = service.hash("123456")

    assert len(code_hash) == 64


def test_verify_accepts_correct_code():
    service = OTPService()

    code = "123456"
    code_hash = service.hash(code)

    assert service.verify(code, code_hash) is True


def test_verify_rejects_wrong_code():
    service = OTPService()

    code_hash = service.hash("123456")

    assert service.verify("654321", code_hash) is False


def test_create_signup_verification():
    service = OTPService()

    now = datetime.now(timezone.utc)

    verification, code = service.create_signup_verification(
        identifier="alice@example.com",
        now=now,
    )

    assert verification.identifier == "alice@example.com"
    assert verification.purpose == VerificationPurpose.SIGNUP
    assert verification.status == VerificationStatus.PENDING

    assert verification.attempt_count == 0
    assert verification.resend_count == 0

    assert verification.code_hash == service.hash(code)

    assert verification.otp_expires_at == now + timedelta(minutes=10)
    assert verification.session_expires_at == now + timedelta(minutes=60)

    assert verification.last_sent_at == now


def test_refresh_signup_verification_preserves_session_state():
    service = OTPService()

    now = datetime.now(timezone.utc)
    original_session_expiry = now + timedelta(minutes=60)

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel=VerificationChannel.EMAIL,
        purpose=VerificationPurpose.SIGNUP,
        code_hash=service.hash("123456"),
        status=VerificationStatus.PENDING,
        attempt_count=2,
        resend_count=1,
        created_at=now - timedelta(minutes=5),
        otp_expires_at=now + timedelta(minutes=5),
        last_sent_at=now - timedelta(minutes=2),
        session_expires_at=original_session_expiry,
    )

    refreshed_verification, new_code = service.refresh_signup_verification(
        verification=existing_verification,
        now=now,
    )

    assert refreshed_verification.code_hash == service.hash(new_code)

    assert refreshed_verification.attempt_count == 2

    assert refreshed_verification.resend_count == 2

    assert refreshed_verification.otp_expires_at == (
        now + timedelta(minutes=10)
    )

    assert refreshed_verification.last_sent_at == now

    assert refreshed_verification.session_expires_at == (
        original_session_expiry
    )

    assert refreshed_verification.status == VerificationStatus.PENDING


def test_prepare_signup_verification_rejects_locked_session():
    service = OTPService()

    now = datetime.now(timezone.utc)

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel=VerificationChannel.EMAIL,
        purpose=VerificationPurpose.SIGNUP,
        code_hash=service.hash("123456"),
        status=VerificationStatus.LOCKED,
        attempt_count=3,
        resend_count=1,
        created_at=now - timedelta(minutes=10),
        otp_expires_at=now - timedelta(minutes=1),
        last_sent_at=now - timedelta(minutes=2),
        session_expires_at=now + timedelta(minutes=50),
    )

    result = service.prepare_signup_verification(
        identifier="alice@example.com",
        existing_verification=existing_verification,
        now=now,
    )

    assert result is None


def test_prepare_signup_verification_starts_new_session_when_expired():
    service = OTPService()

    now = datetime.now(timezone.utc)

    expired_verification = OTPVerification(
        identifier="alice@example.com",
        channel=VerificationChannel.EMAIL,
        purpose=VerificationPurpose.SIGNUP,
        code_hash=service.hash("123456"),
        status=VerificationStatus.LOCKED,
        attempt_count=3,
        resend_count=2,
        created_at=now - timedelta(minutes=70),
        otp_expires_at=now - timedelta(minutes=60),
        last_sent_at=now - timedelta(minutes=60),
        session_expires_at=now - timedelta(minutes=10),
    )

    new_verification, new_code = service.prepare_signup_verification(
        identifier="alice@example.com",
        existing_verification=expired_verification,
        now=now,
    )

    assert new_verification.status == VerificationStatus.PENDING
    assert new_verification.attempt_count == 0
    assert new_verification.resend_count == 0

    assert new_verification.code_hash == service.hash(new_code)

    assert new_verification.created_at == now
    assert new_verification.otp_expires_at == (
        now + timedelta(minutes=10)
    )
    assert new_verification.session_expires_at == (
        now + timedelta(minutes=60)
    )


def test_prepare_signup_verification_rejects_resend_during_cooldown():
    service = OTPService()

    now = datetime.now(timezone.utc)

    existing_verification = OTPVerification(
        identifier="alice@example.com",
        channel=VerificationChannel.EMAIL,
        purpose=VerificationPurpose.SIGNUP,
        code_hash=service.hash("123456"),
        status=VerificationStatus.PENDING,
        attempt_count=1,
        resend_count=0,
        created_at=now - timedelta(minutes=5),
        otp_expires_at=now + timedelta(minutes=5),
        last_sent_at=now - timedelta(seconds=30),
        session_expires_at=now + timedelta(minutes=55),
    )

    result = service.prepare_signup_verification(
        identifier="alice@example.com",
        existing_verification=existing_verification,
        now=now,
    )

    assert result is None