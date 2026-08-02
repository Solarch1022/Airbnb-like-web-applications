from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.dao.item_dao import _from_dynamodb_item, _to_dynamodb_item


class BookingDAO:
    """DynamoDB-backed data access for bookings."""

    def __init__(self, client: Any, table_name: str) -> None:
        self._client = client
        self._table_name = table_name

    def list_bookings(self) -> list[dict[str, Any]]:
        """Scan and return all bookings."""
        bookings: list[dict[str, Any]] = []
        paginator = self._client.get_paginator("scan")

        for page in paginator.paginate(TableName=self._table_name):
            bookings.extend(
                _from_dynamodb_item(raw)
                for raw in page.get("Items", [])
            )

        return bookings

    def get_booking(
        self,
        booking_id: str,
    ) -> dict[str, Any] | None:
        """Return one booking by id, or None if not found."""
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"id": {"S": booking_id}},
        )

        raw = response.get("Item")
        return _from_dynamodb_item(raw) if raw else None

    def put_booking(
        self,
        booking_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Create or overwrite a booking."""
        self._client.put_item(
            TableName=self._table_name,
            Item=_to_dynamodb_item(booking_data),
        )

        return booking_data

    def update_booking(
        self,
        booking_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing booking."""
        return self.put_booking(booking_data)

    def delete_booking(self, booking_id: str) -> bool:
        """Delete a booking and return True if it existed."""
        try:
            response = self._client.delete_item(
                TableName=self._table_name,
                Key={"id": {"S": booking_id}},
                ConditionExpression="attribute_exists(id)",
                ReturnValues="ALL_OLD",
            )
        except ClientError as exc:
            if (
                exc.response["Error"]["Code"]
                == "ConditionalCheckFailedException"
            ):
                return False

            raise

        return "Attributes" in response

    def ensure_table(self) -> None:
        """Create the bookings table if it does not already exist."""
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
                }
            ],
            KeySchema=[
                {
                    "AttributeName": "id",
                    "KeyType": "HASH",
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        self._client.get_waiter("table_exists").wait(
            TableName=self._table_name,
        )


@lru_cache
def get_booking_dao() -> BookingDAO:
    """Return a cached DynamoDB-backed BookingDAO."""
    settings: Settings = get_settings()

    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        endpoint_url=settings.dynamodb_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    return BookingDAO(
        client=client,
        table_name=settings.dynamodb_bookings_table_name,
    )