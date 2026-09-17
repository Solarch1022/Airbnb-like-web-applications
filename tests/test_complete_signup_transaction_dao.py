from datetime import datetime, timedelta, timezone

from app.models.auth import Session, SessionStatus

from app.dao.complete_signup_transaction_dao import (
    CompleteSignupTransactionDAO,
)


class FakeDynamoDBClient:
    def __init__(self):
        self.transact_items = None

    def transact_write_items(self, TransactItems):
        self.transact_items = TransactItems

def make_session(
    account_id: str = "account-001",
) -> Session:
    now = datetime.now(timezone.utc)

    return Session(
        id="session-001",
        account_id=account_id,
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )


def make_complete_signup_dao(
    client: FakeDynamoDBClient,
) -> CompleteSignupTransactionDAO:
    return CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
        sessions_table_name="sessions",
    )

def test_complete_signup_uses_single_dynamodb_transaction():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    assert client.transact_items is not None
    assert len(client.transact_items) == 3

def test_complete_signup_transaction_dao_exists():
    assert CompleteSignupTransactionDAO is not None


def test_complete_signup_transaction_dao_has_complete_signup_method():
    assert hasattr(
        CompleteSignupTransactionDAO,
        "complete_signup",
    )


def test_complete_signup_transaction_updates_correct_account():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    account_operation = client.transact_items[0]

    assert "Update" in account_operation
    assert (
        account_operation["Update"]["TableName"]
        == "accounts"
    )
    assert account_operation["Update"]["Key"] == {
        "id": {"S": "account-001"}
    }


def test_complete_signup_requires_account_pending_setup():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    account_update = client.transact_items[0]["Update"]

    assert (
        account_update["ConditionExpression"]
        == "#status = :pending_setup"
    )

    assert account_update["ExpressionAttributeNames"][
        "#status"
    ] == "status"

    assert account_update["ExpressionAttributeValues"][
        ":pending_setup"
    ] == {
        "S": "pending_setup"
    }


def test_complete_signup_updates_account_profile_password_and_status():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    account_update = client.transact_items[0]["Update"]

    update_expression = account_update[
        "UpdateExpression"
    ]

    assert "first_name = :first_name" in update_expression
    assert "last_name = :last_name" in update_expression
    assert "password_hash = :password_hash" in update_expression
    assert "#status = :active" in update_expression

    values = account_update[
        "ExpressionAttributeValues"
    ]

    assert values[":first_name"] == {
        "S": "Alice"
    }
    assert values[":last_name"] == {
        "S": "Test"
    }
    assert values[":password_hash"] == {
        "S": "hashed-password"
    }
    assert values[":active"] == {
        "S": "active"
    }


def test_complete_signup_updates_account_updated_at():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    account_update = client.transact_items[0]["Update"]

    assert "updated_at = :updated_at" in (
        account_update["UpdateExpression"]
    )

    updated_at = account_update[
        "ExpressionAttributeValues"
    ][":updated_at"]

    assert "S" in updated_at
    assert updated_at["S"]


def test_complete_signup_transaction_updates_correct_registration_token():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    token_operation = client.transact_items[1]

    assert "Update" in token_operation

    assert (
        token_operation["Update"]["TableName"]
        == "registration_tokens"
    )

    assert token_operation["Update"]["Key"] == {
        "jti": {
            "S": "token-jti-001",
        }
    }


def test_complete_signup_requires_registration_token_active():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    token_update = client.transact_items[1]["Update"]

    assert (
        token_update["ConditionExpression"]
        == "#status = :active"
    )

    assert token_update["ExpressionAttributeNames"][
        "#status"
    ] == "status"

    assert token_update["ExpressionAttributeValues"][
        ":active"
    ] == {
        "S": "active"
    }


def test_complete_signup_consumes_registration_token():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    token_update = client.transact_items[1]["Update"]

    assert (
        token_update["UpdateExpression"]
        == "SET #status = :consumed"
    )

    assert token_update["ExpressionAttributeValues"][
        ":consumed"
    ] == {
        "S": "consumed"
    }


def test_complete_signup_transaction_includes_session():
    client = FakeDynamoDBClient()

    dao = make_complete_signup_dao(client)

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=session,
    )

    assert client.transact_items is not None
    assert len(client.transact_items) == 3

    session_operation = client.transact_items[2]

    assert "Put" in session_operation

    session_put = session_operation["Put"]

    assert session_put["TableName"] == "sessions"

    assert session_put["Item"] == {
        "id": {
            "S": "session-001",
        },
        "account_id": {
            "S": "account-001",
        },
        "status": {
            "S": "active",
        },
        "created_at": {
            "S": now.isoformat(),
        },
        "expires_at": {
            "S": (
                now + timedelta(days=30)
            ).isoformat(),
        },
        "ttl": {
            "N": str(
                int(
                    (
                        now + timedelta(days=30)
                    ).timestamp()
                )
            ),
        },
    }


def test_complete_signup_does_not_overwrite_existing_session():
    client = FakeDynamoDBClient()
    dao = make_complete_signup_dao(client)

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
        session=make_session(),
    )

    session_put = client.transact_items[2]["Put"]

    assert (
        session_put["ConditionExpression"]
        == "attribute_not_exists(id)"
    )