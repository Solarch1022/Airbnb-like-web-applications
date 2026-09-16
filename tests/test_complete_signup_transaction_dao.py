from app.dao.complete_signup_transaction_dao import (
    CompleteSignupTransactionDAO,
)


class FakeDynamoDBClient:
    def __init__(self):
        self.transact_items = None

    def transact_write_items(self, TransactItems):
        self.transact_items = TransactItems


def test_complete_signup_uses_single_dynamodb_transaction():
    client = FakeDynamoDBClient()

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
    )

    assert client.transact_items is not None
    assert len(client.transact_items) == 2

def test_complete_signup_transaction_dao_exists():
    assert CompleteSignupTransactionDAO is not None


def test_complete_signup_transaction_dao_has_complete_signup_method():
    assert hasattr(
        CompleteSignupTransactionDAO,
        "complete_signup",
    )


def test_complete_signup_transaction_updates_correct_account():
    client = FakeDynamoDBClient()

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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

    dao = CompleteSignupTransactionDAO(
        client=client,
        accounts_table_name="accounts",
        registration_tokens_table_name="registration_tokens",
    )

    dao.complete_signup(
        account_id="account-001",
        registration_token_jti="token-jti-001",
        first_name="Alice",
        last_name="Test",
        password_hash="hashed-password",
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