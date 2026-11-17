from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.dao.session_dao import (
    SessionDAO,
    get_session_dao,
)
from app.models.auth import Session, SessionStatus

from botocore.exceptions import ClientError


class FakeClient:
    def __init__(self):
        self.put_item_call = None
        self.get_item_response = {}

    def put_item(
        self,
        TableName,
        Item,
        ConditionExpression=None,
    ):
        self.put_item_call = {
            "TableName": TableName,
            "Item": Item,
            "ConditionExpression": ConditionExpression,
        }

    def get_item(
        self,
        TableName,
        Key,
    ):
        return self.get_item_response

class FakeWaiter:
    def __init__(self):
        self.wait_call = None

    def wait(self, **kwargs):
        self.wait_call = kwargs


class FakeDynamoDBClient:
    def __init__(
        self,
        table_exists: bool = True,
    ):
        self.table_exists = table_exists
        self.create_table_call = None
        self.waiter = FakeWaiter()
        self.update_time_to_live_call = None
        self.ttl_description = {"TimeToLiveStatus": "DISABLED"}

    def describe_time_to_live(self, TableName):
        return {"TimeToLiveDescription": self.ttl_description}

    def update_time_to_live(
        self,
        **kwargs,
    ):
        self.update_time_to_live_call = kwargs
        self.ttl_description = {"TimeToLiveStatus": "ENABLED", "AttributeName": "ttl"}

    def describe_table(self, TableName):
        if not self.table_exists:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ResourceNotFoundException",
                        "Message": "Table not found",
                    }
                },
                "DescribeTable",
            )

        return {
            "Table": {
                "TableName": TableName,
            }
        }

    def create_table(self, **kwargs):
        self.create_table_call = kwargs

    def get_waiter(self, waiter_name):
        return self.waiter


def test_put_session_persists_session():
    client = FakeClient()

    dao = SessionDAO(
        client=client,
        table_name="sessions",
    )

    now = datetime.now(timezone.utc)

    session = Session(
        id="session-001",
        account_id="account-001",
        status=SessionStatus.ACTIVE,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )

    dao.put_session(session)

    assert client.put_item_call["TableName"] == "sessions"
    assert client.put_item_call["Item"] == {
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

    assert (
        client.put_item_call["ConditionExpression"]
        == "attribute_not_exists(id)"
    )


def test_get_session_returns_session():
    client = FakeClient()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=30)

    client.get_item_response = {
        "Item": {
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
                "S": expires_at.isoformat(),
            },
            "ttl": {
                "N": str(
                    int(expires_at.timestamp())
                ),
            },
        }
    }

    dao = SessionDAO(
        client=client,
        table_name="sessions",
    )

    session = dao.get_session("session-001")

    assert session is not None
    assert session.id == "session-001"
    assert session.account_id == "account-001"
    assert session.status == SessionStatus.ACTIVE
    assert session.created_at == now
    assert session.expires_at == expires_at

def test_get_session_returns_none_when_session_does_not_exist():
    client = FakeClient()
    client.get_item_response = {}

    dao = SessionDAO(
        client=client,
        table_name="sessions",
    )

    session = dao.get_session("missing-session")

    assert session is None

def test_get_session_dao_factory_returns_session_dao():
    get_session_dao.cache_clear()

    dao = get_session_dao()

    assert isinstance(dao, SessionDAO)


def test_ensure_table_does_not_create_table_when_table_exists():
    client = FakeDynamoDBClient()

    dao = SessionDAO(
        client=client,
        table_name="sessions",
    )

    dao.ensure_table()

    assert client.create_table_call is None

    assert client.update_time_to_live_call == {
        "TableName": "sessions",
        "TimeToLiveSpecification": {
            "Enabled": True,
            "AttributeName": "ttl",
        },
    }


def test_ensure_table_creates_table_when_table_does_not_exist():
    client = FakeDynamoDBClient(
        table_exists=False,
    )

    dao = SessionDAO(
        client=client,
        table_name="sessions",
    )

    dao.ensure_table()

    assert client.create_table_call == {
        "TableName": "sessions",
        "AttributeDefinitions": [
            {
                "AttributeName": "id",
                "AttributeType": "S",
            },
        ],
        "KeySchema": [
            {
                "AttributeName": "id",
                "KeyType": "HASH",
            },
        ],
        "BillingMode": "PAY_PER_REQUEST",
    }

    assert client.waiter.wait_call == {
        "TableName": "sessions",
    }

    assert client.update_time_to_live_call == {
        "TableName": "sessions",
        "TimeToLiveSpecification": {
            "Enabled": True,
            "AttributeName": "ttl",
        },
    }


@pytest.mark.parametrize("ttl_status", ["ENABLED", "ENABLING"])
def test_ensure_table_skips_already_configured_ttl(ttl_status):
    client = FakeDynamoDBClient()
    client.ttl_description = {"TimeToLiveStatus": ttl_status, "AttributeName": "ttl"}
    SessionDAO(client, "sessions").ensure_table()
    assert client.create_table_call is None
    assert client.update_time_to_live_call is None


def test_repeated_bootstrap_enables_ttl_only_once():
    client = FakeDynamoDBClient()
    original_update = client.update_time_to_live
    client.update_time_to_live = Mock(side_effect=original_update)
    dao = SessionDAO(client, "sessions")
    dao.ensure_table()
    dao.ensure_table()
    assert client.update_time_to_live.call_count == 1


@pytest.mark.parametrize("description", [
    {"TimeToLiveStatus": "ENABLED", "AttributeName": "wrong"},
    {"TimeToLiveStatus": "ENABLING", "AttributeName": "wrong"},
    {"TimeToLiveStatus": "DISABLING", "AttributeName": "ttl"},
])
def test_bootstrap_does_not_silently_accept_incompatible_ttl(description):
    client = FakeDynamoDBClient()
    client.ttl_description = description
    with pytest.raises(RuntimeError):
        SessionDAO(client, "sessions").ensure_table()
    assert client.update_time_to_live_call is None


def test_concurrent_ttl_enable_is_verified_after_validation_error():
    client = FakeDynamoDBClient()
    client.describe_time_to_live = Mock(side_effect=[
        {"TimeToLiveDescription": {"TimeToLiveStatus": "DISABLED"}},
        {"TimeToLiveDescription": {"TimeToLiveStatus": "ENABLING", "AttributeName": "ttl"}},
    ])
    client.update_time_to_live = Mock(side_effect=ClientError(
        {"Error": {"Code": "ValidationException"}}, "UpdateTimeToLive",
    ))
    SessionDAO(client, "sessions").ensure_table()
    assert client.describe_time_to_live.call_count == 2


@pytest.mark.parametrize("code", ["ValidationException", "AccessDeniedException", "InternalServerError"])
def test_ttl_configuration_failure_is_not_swallowed(code):
    client = FakeDynamoDBClient()
    error = ClientError({"Error": {"Code": code}}, "UpdateTimeToLive")
    client.update_time_to_live = Mock(side_effect=error)
    with pytest.raises(ClientError) as caught:
        SessionDAO(client, "sessions").ensure_table()
    assert caught.value is error
