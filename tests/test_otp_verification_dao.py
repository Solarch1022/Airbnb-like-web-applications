from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.dao.otp_verification_dao import OTPVerificationDAO
from app.models.auth import VerificationPurpose, VerificationStatus


def _pending_verification_attributes(attempt_count: int) -> dict:
    return {
        "identifier": {"S": "alice@example.com"},
        "channel": {"S": "email"},
        "purpose": {"S": "signup"},
        "code_hash": {"S": "hashed-code"},
        "status": {"S": "pending"},
        "attempt_count": {"N": str(attempt_count)},
        "resend_count": {"N": "0"},
        "created_at": {"S": "2026-08-28T10:00:00+00:00"},
        "otp_expires_at": {"S": "2026-08-28T10:10:00+00:00"},
        "last_sent_at": {"S": "2026-08-28T10:00:00+00:00"},
        "session_expires_at": {"S": "2026-08-28T11:00:00+00:00"},
    }


def test_record_failed_attempt_increments_from_zero_to_one() -> None:
    client = MagicMock()

    client.update_item.side_effect = [
        ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "not third attempt",
                }
            },
            "UpdateItem",
        ),
        {
            "Attributes": _pending_verification_attributes(
                attempt_count=1,
            )
        },
    ]

    dao = OTPVerificationDAO(
        client=client,
        table_name="otp_verifications",
    )

    verification = dao.record_failed_attempt(
        identifier="alice@example.com",
        purpose=VerificationPurpose.SIGNUP,
    )

    assert verification.attempt_count == 1
    assert verification.status == VerificationStatus.PENDING
    assert client.update_item.call_count == 2


def test_record_failed_attempt_increments_from_one_to_two() -> None:
    client = MagicMock()

    client.update_item.side_effect = [
        ClientError(
            {
                "Error": {
                    "Code": "ConditionalCheckFailedException",
                    "Message": "not third attempt",
                }
            },
            "UpdateItem",
        ),
        {
            "Attributes": _pending_verification_attributes(
                attempt_count=2,
            )
        },
    ]

    dao = OTPVerificationDAO(
        client=client,
        table_name="otp_verifications",
    )

    verification = dao.record_failed_attempt(
        identifier="alice@example.com",
        purpose=VerificationPurpose.SIGNUP,
    )

    assert verification.attempt_count == 2
    assert verification.status == VerificationStatus.PENDING
    assert client.update_item.call_count == 2


def test_record_failed_attempt_locks_on_third_attempt() -> None:
    client = MagicMock()

    attributes = _pending_verification_attributes(
        attempt_count=3,
    )
    attributes["status"] = {
        "S": VerificationStatus.LOCKED.value,
    }

    client.update_item.return_value = {
        "Attributes": attributes
    }

    dao = OTPVerificationDAO(
        client=client,
        table_name="otp_verifications",
    )

    verification = dao.record_failed_attempt(
        identifier="alice@example.com",
        purpose=VerificationPurpose.SIGNUP,
    )

    assert verification.attempt_count == 3
    assert verification.status == VerificationStatus.LOCKED
    assert client.update_item.call_count == 1