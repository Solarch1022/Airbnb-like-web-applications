from datetime import datetime, timedelta, timezone

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

    def update_time_to_live(
        self,
        **kwargs,
    ):
        self.update_time_to_live_call = kwargs

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