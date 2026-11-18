import boto3

from enum import Enum
from typing import Any

from boto3.dynamodb.types import (
    TypeDeserializer,
    TypeSerializer,
)

from datetime import datetime
from functools import lru_cache
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.models.auth import Session

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _prepare_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    return value


def _to_dynamodb_item(
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: _serializer.serialize(
            _prepare_value(value)
        )
        for key, value in data.items()
        if value is not None
    }

def _from_dynamodb_item(
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: _deserializer.deserialize(value)
        for key, value in item.items()
    }

class SessionDAO:

    def __init__(
        self,
        client,
        table_name: str,
    ) -> None:
        self._client = client
        self._table_name = table_name

    def put_session(
        self,
        session: Session,
    ) -> None:
        data = session.model_dump()

        data["ttl"] = int(
            session.expires_at.timestamp()
        )

        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(data),
            ConditionExpression="attribute_not_exists(id)",
        )

    def get_session(
        self,
        session_id: str,
    ) -> Session | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                "id": {
                    "S": session_id,
                },
            },
        )

        item = response.get("Item")

        if not item:
            return None

        return Session.model_validate(
            _from_dynamodb_item(item)
        )

    def ensure_table(self) -> None:
        try:
            self._client.describe_table(
                TableName=self._table_name
            )

        except ClientError as exc:
            if (
                exc.response["Error"]["Code"]
                != "ResourceNotFoundException"
            ):
                raise

            self._client.create_table(
                TableName=self._table_name,
                AttributeDefinitions=[
                    {
                        "AttributeName": "id",
                        "AttributeType": "S",
                    },
                ],
                KeySchema=[
                    {
                        "AttributeName": "id",
                        "KeyType": "HASH",
                    },
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            self._client.get_waiter(
                "table_exists"
            ).wait(
                TableName=self._table_name
            )

        self._ensure_ttl()

    def _ttl_is_configured(self) -> bool:
        description = self._client.describe_time_to_live(
            TableName=self._table_name,
        )["TimeToLiveDescription"]
        ttl_status = description["TimeToLiveStatus"]
        if ttl_status in ("ENABLED", "ENABLING"):
            if description.get("AttributeName") != "ttl":
                raise RuntimeError(
                    f"Session table {self._table_name} has TTL configured on a different attribute"
                )
            return True
        if ttl_status != "DISABLED":
            raise RuntimeError(
                f"Session table {self._table_name} TTL is {ttl_status}; retry after the transition completes"
            )
        return False

    def _ensure_ttl(self) -> None:
        if self._ttl_is_configured():
            return
        try:
            self._client.update_time_to_live(
                TableName=self._table_name,
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": "ttl",
                },
            )
        except ClientError as exc:
            # Another startup may have enabled TTL after our describe call.
            # Only accept the error if the desired configuration is now present.
            if exc.response["Error"]["Code"] != "ValidationException":
                raise
            if not self._ttl_is_configured():
                raise


@lru_cache
def get_session_dao() -> SessionDAO:
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return SessionDAO(
        client=client,
        table_name=settings.dynamodb_sessions_table_name,
    )