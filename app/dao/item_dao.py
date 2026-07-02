"""Data Access Object (DAO) for items, backed by AWS DynamoDB.

This layer is the only place that talks to DynamoDB via the boto3 client.
It translates between DynamoDB's attribute-typed item representation and our
plain Python dicts, keeping the service layer storage-agnostic.

The table is assumed to have a string partition key named ``id``.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _to_dynamodb_item(data: dict[str, Any]) -> dict[str, Any]:
    """Serialize a plain dict into DynamoDB's attribute-value format.

    Floats are converted to ``Decimal`` because DynamoDB does not accept
    native floats.
    """
    prepared = {
        key: (Decimal(str(value)) if isinstance(value, float) else value)
        for key, value in data.items()
        if value is not None
    }
    return {key: _serializer.serialize(value) for key, value in prepared.items()}


def _from_dynamodb_item(item: dict[str, Any]) -> dict[str, Any]:
    """Deserialize a DynamoDB attribute-value item into a plain dict.

    ``Decimal`` values are converted back to ``int``/``float``.
    """
    result: dict[str, Any] = {}
    for key, value in item.items():
        deserialized = _deserializer.deserialize(value)
        if isinstance(deserialized, Decimal):
            deserialized = int(deserialized) if deserialized % 1 == 0 else float(deserialized)
        result[key] = deserialized
    return result


class ItemDAO:
    """DynamoDB-backed data access for items."""

    def __init__(self, client: Any, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    def list_items(self) -> list[dict[str, Any]]:
        """Scan and return all items in the table.

        Note: ``scan`` reads the whole table and is fine for small datasets
        or demos; use a Query with proper keys/indexes at scale.
        """
        items: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("scan")
        for page in paginator.paginate(TableName=self._table_name):
            items.extend(_from_dynamodb_item(raw) for raw in page.get("Items", []))
        return items

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        """Return a single item by id, or None if not found."""
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"id": {"S": item_id}},
        )
        raw = response.get("Item")
        return _from_dynamodb_item(raw) if raw else None

    def put_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Create or overwrite an item. Returns the stored item."""
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(item),
        )
        return item

    def delete_item(self, item_id: str) -> bool:
        """Delete an item by id. Returns True if it existed.

        Uses a conditional delete and ``ReturnValues`` to detect existence.
        """
        try:
            response = self._client.delete_item(
                TableName=self._table_name,
                Key={"id": {"S": item_id}},
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise
        return "Attributes" in response

    def ensure_table(self) -> None:
        """Create the table if it does not already exist.

        Intended for local development and integration tests. In production,
        tables should be provisioned via infrastructure-as-code, not by the app.
        The table uses a single string partition key named ``id``.
        """
        try:
            self._client.describe_table(TableName=self._table_name)
            return  # Already exists.
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        self._client.create_table(
            TableName=self._table_name,
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # Block until the table is ready to serve reads/writes.
        self._client.get_waiter("table_exists").wait(TableName=self._table_name)


@lru_cache
def get_item_dao() -> ItemDAO:
    """Dependency provider returning a cached, DynamoDB-backed ItemDAO."""
    settings: Settings = get_settings()
    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
    )
    return ItemDAO(client=client, table_name=settings.dynamodb_table_name)
