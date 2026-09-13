from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.models.account import Account


_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _prepare_value(value: Any) -> Any:

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, float):
        return Decimal(str(value))

    return value


def _to_dynamodb_item(data: dict[str, Any]) -> dict[str, Any]:

    return {
        key: _serializer.serialize(_prepare_value(value))
        for key, value in data.items()
        if value is not None
    }


def _from_dynamodb_item(item: dict[str, Any]) -> dict[str, Any]:

    return {
        key: _deserializer.deserialize(value)
        for key, value in item.items()
    }


class AccountDAO:

    def __init__(
        self, 
        client: Any, 
        table_name: str
    ) -> None:
        self._client = client
        self._table_name = table_name

    def get_account(
        self,
        account_id: str,
    ) -> Account | None:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"id": {"S": account_id}},
        )

        item = response.get("Item")

        if not item:
            return None

        return Account.model_validate(
            _from_dynamodb_item(item)
        )

    def get_account_by_email(
        self,
        email: str,
    ) -> Account | None:
        response = self._client.query(
            TableName=self._table_name,
            IndexName="email-index",
            KeyConditionExpression="email = :email",
            ExpressionAttributeValues={
                ":email": {"S": email.lower()},
            },
            Limit=1,
        )

        items = response.get("Items", [])

        if not items:
            return None

        return Account.model_validate(
            _from_dynamodb_item(items[0])
        )

    def put_account(
        self,
        account: Account,
    ) -> Account:
        
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(account.model_dump()),
        )

        return account

    def ensure_table(self) -> None:
        try:
            self._client.describe_table(
                TableName=self._table_name,
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
                    "AttributeName": "id",
                    "AttributeType": "S",
                },
                {
                    "AttributeName": "email",
                    "AttributeType": "S",
                },
            ],

            KeySchema=[
                {
                    "AttributeName": "id",
                    "KeyType": "HASH",
                },
            ],

            GlobalSecondaryIndexes=[
                {
                    "IndexName": "email-index",

                    "KeySchema": [
                        {
                            "AttributeName": "email",
                            "KeyType": "HASH",
                        },
                    ],

                    "Projection": {
                        "ProjectionType": "ALL",
                    },
                },
            ],

            BillingMode="PAY_PER_REQUEST",
        )

        self._client.get_waiter("table_exists").wait(
            TableName=self._table_name
        )


@lru_cache
def get_account_dao() -> AccountDAO:

    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return AccountDAO(
        client=client,
        table_name=settings.dynamodb_accounts_table_name,
    )