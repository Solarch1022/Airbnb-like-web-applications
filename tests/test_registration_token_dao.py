from datetime import datetime, timedelta, timezone

from app.dao.registration_token_dao import RegistrationTokenDAO
from botocore.exceptions import ClientError
from app.models.auth import (
    RegistrationToken,
    RegistrationTokenStatus,
)


class FakeDynamoDBClient:

    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        jti = Item["jti"]["S"]
        self.items[jti] = Item

    def get_item(self, TableName, Key):
        jti = Key["jti"]["S"]

        item = self.items.get(jti)

        if item is None:
            return {}

        return {
            "Item": item,
        }

    def update_item(
        self,
        TableName,
        Key,
        UpdateExpression,
        ConditionExpression,
        ExpressionAttributeNames,
        ExpressionAttributeValues,
        ReturnValues,
    ):
        jti = Key["jti"]["S"]
        item = self.items.get(jti)

        if item is None:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "Token does not exist",
                    }
                },
                "UpdateItem",
            )

        status_name = ExpressionAttributeNames["#status"]
        active_value = ExpressionAttributeValues[":active"]["S"]
        consumed_value = ExpressionAttributeValues[":consumed"]["S"]

        if item[status_name]["S"] != active_value:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ConditionalCheckFailedException",
                        "Message": "Token already consumed",
                    }
                },
                "UpdateItem",
            )

        item[status_name] = {
            "S": consumed_value,
        }

        return {
            "Attributes": item,
        }


def test_put_and_get_registration_token():
    client = FakeDynamoDBClient()

    dao = RegistrationTokenDAO(
        client=client,
        table_name="registration_tokens",
    )

    now = datetime.now(timezone.utc)

    token = RegistrationToken(
        jti="test-jti-123",
        account_id="account-123",
        email="user@example.com",
        status=RegistrationTokenStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
    )

    dao.put_token(token)

    stored = dao.get_token("test-jti-123")

    assert stored is not None
    assert stored.jti == "test-jti-123"
    assert stored.account_id == "account-123"
    assert stored.email == "user@example.com"
    assert stored.status == RegistrationTokenStatus.ACTIVE


def test_consume_registration_token():
    client = FakeDynamoDBClient()

    dao = RegistrationTokenDAO(
        client=client,
        table_name="registration_tokens",
    )

    now = datetime.now(timezone.utc)

    token = RegistrationToken(
        jti="test-jti-123",
        account_id="account-123",
        email="user@example.com",
        status=RegistrationTokenStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
    )

    dao.put_token(token)

    consumed = dao.consume_token("test-jti-123")

    assert consumed is True

    stored = dao.get_token("test-jti-123")

    assert stored is not None
    assert stored.status == RegistrationTokenStatus.CONSUMED


def test_registration_token_cannot_be_consumed_twice():
    client = FakeDynamoDBClient()

    dao = RegistrationTokenDAO(
        client=client,
        table_name="registration_tokens",
    )

    now = datetime.now(timezone.utc)

    token = RegistrationToken(
        jti="test-jti-123",
        account_id="account-123",
        email="user@example.com",
        status=RegistrationTokenStatus.ACTIVE,
        expires_at=now + timedelta(minutes=10),
    )

    dao.put_token(token)

    first_result = dao.consume_token("test-jti-123")
    second_result = dao.consume_token("test-jti-123")

    assert first_result is True
    assert second_result is False