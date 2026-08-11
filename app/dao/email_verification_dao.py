"""Data access for email verification records stored in DynamoDB."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any
from enum import Enum

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _prepare_value(value: Any) -> Any:
    """Convert values that DynamoDB cannot store directly."""
    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Enum):
        return value.value

    return value


def _to_dynamodb_item(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize a verification record for DynamoDB."""
    return {
        key: _serializer.serialize(_prepare_value(value))
        for key, value in data.items()
        if value is not None
    }


def _from_dynamodb_item(item: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a DynamoDB verification record."""
    return {
        key: _deserializer.deserialize(value)
        for key, value in item.items()
    }


class EmailVerificationDAO:
    """DynamoDB-backed data access for email verification records."""

    def __init__(self, client: Any, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    def get_verification(self, email: str) -> dict[str, Any] | None:
        """Return the verification record for an email."""
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"email": {"S": email}},
        )

        item = response.get("Item")

        return _from_dynamodb_item(item) if item else None

    def put_verification(
        self,
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        """Create or replace an email verification record."""
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(verification),
        )

        return verification

    def update_verification(
        self,
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an email verification record."""
        return self.put_verification(verification)

    def delete_verification(self, email: str) -> bool:
        """Delete an email verification record."""
        try:
            response = self._client.delete_item(
                TableName=self._table_name,
                Key={"email": {"S": email}},
                ConditionExpression="attribute_exists(email)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

        return "Attributes" in response

    def ensure_table(self) -> None:
        """Create the email verification table if it does not exist."""
        try:
            self._client.describe_table(TableName=self._table_name)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        self._client.create_table(
            TableName=self._table_name,
            AttributeDefinitions=[
                {
                    "AttributeName": "email",
                    "AttributeType": "S",
                }
            ],
            KeySchema=[
                {
                    "AttributeName": "email",
                    "KeyType": "HASH",
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        self._client.get_waiter("table_exists").wait(
            TableName=self._table_name
        )


@lru_cache
def get_email_verification_dao() -> EmailVerificationDAO:
    """Return the configured email verification DAO."""
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return EmailVerificationDAO(
        client=client,
        table_name=settings.dynamodb_email_verifications_table_name,
    )