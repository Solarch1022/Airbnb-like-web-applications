"""Data Access Object (DAO) for users, backed by AWS DynamoDB."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.dao.item_dao import _from_dynamodb_item, _to_dynamodb_item


class UserDAO:
    """DynamoDB-backed data access for users."""

    def __init__(self, client: Any, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    def list_users(self) -> list[dict[str, Any]]:
        """Scan and return all users."""
        users: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("scan")

        for page in paginator.paginate(TableName=self._table_name):
            users.extend(
                _from_dynamodb_item(raw)
                for raw in page.get("Items", [])
            )

        return users

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Return a single user by id, or None if not found."""
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"id": {"S": user_id}},
        )

        raw = response.get("Item")
        return _from_dynamodb_item(raw) if raw else None

    def put_user(self, user: dict[str, Any]) -> dict[str, Any]:
        """Create or overwrite a user and return the stored data."""
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(user),
        )
        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a user by id and return True if the user existed."""
        try:
            response = self._client.delete_item(
                TableName=self._table_name,
                Key={"id": {"S": user_id}},
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

        return "Attributes" in response

    def ensure_table(self) -> None:
        """Create the users table if it does not already exist."""
        try:
            self._client.describe_table(TableName=self._table_name)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        self._client.create_table(
            TableName=self._table_name,
            AttributeDefinitions=[
                {"AttributeName": "id", "AttributeType": "S"}
            ],
            KeySchema=[
                {"AttributeName": "id", "KeyType": "HASH"}
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        self._client.get_waiter("table_exists").wait(
            TableName=self._table_name
        )


@lru_cache
def get_user_dao() -> UserDAO:
    """Return a cached DynamoDB-backed UserDAO."""
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return UserDAO(
        client=client,
        table_name=settings.dynamodb_users_table_name,
    )