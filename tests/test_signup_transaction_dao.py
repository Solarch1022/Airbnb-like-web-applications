from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.dao.signup_transaction_dao import SignupTransactionDAO
from app.models.auth import VerificationPurpose


def test_activate_account_and_consume_verification_uses_transaction():
    client = MagicMock()

    dao = SignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        otp_verifications_table_name="otp_verifications",
    )

    now = datetime.now(timezone.utc)

    dao.activate_account_and_consume_verification(
        account_id="account-001",
        identifier="alice@example.com",
        purpose=VerificationPurpose.SIGNUP,
        code_hash="expected-code-hash",
        updated_at=now,
    )

    client.transact_write_items.assert_called_once()

    transaction = client.transact_write_items.call_args.kwargs[
        "TransactItems"
    ]

    assert len(transaction) == 2

    account_update = transaction[0]["Update"]
    verification_update = transaction[1]["Update"]

    assert account_update["TableName"] == "accounts"
    assert account_update["Key"] == {
        "id": {"S": "account-001"},
    }

    assert verification_update["TableName"] == "otp_verifications"
    assert verification_update["Key"] == {
        "identifier": {"S": "alice@example.com"},
        "purpose": {"S": "signup"},
    }

    assert account_update["UpdateExpression"] == (
        "SET #status = :active, "
        "updated_at = :updated_at"
    )

    assert account_update["ConditionExpression"] == (
        "#status = :unverified"
    )

    assert account_update["ExpressionAttributeValues"][":active"] == {
        "S": "active",
    }

    assert account_update["ExpressionAttributeValues"][":unverified"] == {
        "S": "unverified",
    }

    assert account_update["ExpressionAttributeValues"][":updated_at"] == {
        "S": now.isoformat(),
    }

    assert verification_update["UpdateExpression"] == (
        "SET #status = :consumed"
    )

    assert verification_update["ConditionExpression"] == (
        "#status = :pending "
        "AND code_hash = :code_hash "
        "AND expires_at > :now "
        "AND session_expires_at > :now"
    )

    assert verification_update["ExpressionAttributeValues"][":now"] == {
        "S": now.isoformat(),
    }
    
    assert verification_update["ExpressionAttributeValues"][":code_hash"] == {
        "S": "expected-code-hash",
    }

    assert verification_update["ExpressionAttributeValues"][":consumed"] == {
        "S": "consumed",
    }

    assert verification_update["ExpressionAttributeValues"][":pending"] == {
        "S": "pending",
    }