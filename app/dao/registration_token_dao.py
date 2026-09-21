from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from functools import lru_cache

import boto3

from app.core.config import Settings, get_settings

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from botocore.exceptions import ClientError

from app.models.auth import (
    RegistrationToken,
    RegistrationTokenStatus,
)


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


class RegistrationTokenDAO:

    def __init__(
        self,
        client: Any,
        table_name: str,
    ) -> None:
        self._client = client
        self._table_name = table_name

    def put_token(
        self,
        token: RegistrationToken,
    ) -> RegistrationToken:
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(
                token.model_dump()
            ),
        )

        return token

    def get_token(
        self,
        jti: str,
    ) -> RegistrationToken | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                "jti": {
                    "S": jti,
                },
            },
        )

        item = response.get("Item")

        if not item:
            return None

        return RegistrationToken.model_validate(
            _from_dynamodb_item(item)
        )

    def consume_token(
        self,
        jti: str,
    ) -> bool:
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={
                    "jti": {
                        "S": jti,
                    },
                },
                UpdateExpression=(
                    "SET #status = :consumed"
                ),
                ConditionExpression=(
                    "#status = :active"
                ),
                ExpressionAttributeNames={
                    "#status": "status",
                },
                ExpressionAttributeValues={
                    ":active": {
                        "S": RegistrationTokenStatus.ACTIVE.value,
                    },
                    ":consumed": {
                        "S": RegistrationTokenStatus.CONSUMED.value,
                    },
                },
                ReturnValues="ALL_NEW",
            )

        except ClientError as exc:
            if (
                exc.response["Error"]["Code"]
                == "ConditionalCheckFailedException"
            ):
                return False

            raise

        return True

    def ensure_table(self) -> None:
        try:
            self._client.describe_table(
                TableName=self._table_name
            )
            return

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
                    "AttributeName": "jti",
                    "AttributeType": "S",
                },
            ],
            KeySchema=[
                {
                    "AttributeName": "jti",
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

@lru_cache
def get_registration_token_dao() -> RegistrationTokenDAO:
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return RegistrationTokenDAO(
        client=client,
        table_name=settings.dynamodb_registration_tokens_table_name,
    )