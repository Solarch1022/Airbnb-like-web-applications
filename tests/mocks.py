"""Reusable test doubles for DynamoDB.

Two levels of mock are provided:

* ``FakeItemDAO`` - a stand-in for :class:`app.dao.item_dao.ItemDAO`. Use it to
  test the service/router layers without exercising any boto3 serialization.
* ``FakeDynamoDBClient`` - a stand-in for the low-level ``boto3.client("dynamodb")``.
  Use it to test the *real* ``ItemDAO`` (including its attribute-value
  serialization) without talking to AWS. It implements just enough of the
  DynamoDB client surface used by the DAO: ``put_item``, ``get_item``,
  ``delete_item`` and ``get_paginator("scan")``.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError


class FakeItemDAO:
    """In-memory stand-in for ItemDAO with the same interface."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def list_items(self) -> list[dict[str, Any]]:
        return list(self._store.values())

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        return self._store.get(item_id)

    def put_item(self, item: dict[str, Any]) -> dict[str, Any]:
        self._store[item["id"]] = item
        return item

    def delete_item(self, item_id: str) -> bool:
        return self._store.pop(item_id, None) is not None


class _FakeScanPaginator:
    """Minimal paginator returning all stored items in a single page."""

    def __init__(self, table: dict[str, dict[str, Any]]) -> None:
        self._table = table

    def paginate(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [{"Items": list(self._table.values())}]


class FakeDynamoDBClient:
    """In-memory fake of the low-level boto3 DynamoDB client.

    Stores items keyed by their ``id`` partition key, in the same
    attribute-value shape the real client uses (e.g. ``{"id": {"S": "x1"}}``).
    """

    def __init__(self) -> None:
        # Maps the raw ``id`` string -> the full attribute-value item dict.
        self._table: dict[str, dict[str, Any]] = {}
        # Records calls for assertions in tests.
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def put_item(self, *, TableName: str, Item: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append(("put_item", {"TableName": TableName, "Item": Item}))
        item_id = Item["id"]["S"]
        self._table[item_id] = Item
        return {}

    def get_item(self, *, TableName: str, Key: dict[str, Any], **_: Any) -> dict[str, Any]:
        self.calls.append(("get_item", {"TableName": TableName, "Key": Key}))
        item_id = Key["id"]["S"]
        stored = self._table.get(item_id)
        return {"Item": stored} if stored is not None else {}

    def delete_item(
        self,
        *,
        TableName: str,
        Key: dict[str, Any],
        ConditionExpression: str | None = None,
        ReturnValues: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        self.calls.append(("delete_item", {"TableName": TableName, "Key": Key}))
        item_id = Key["id"]["S"]
        existing = self._table.pop(item_id, None)
        if existing is None:
            if ConditionExpression:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ConditionalCheckFailedException",
                            "Message": "The conditional request failed",
                        }
                    },
                    "DeleteItem",
                )
            return {}
        return {"Attributes": existing} if ReturnValues == "ALL_OLD" else {}

    def get_paginator(self, operation_name: str) -> _FakeScanPaginator:
        if operation_name != "scan":
            raise NotImplementedError(f"Paginator for {operation_name!r} not supported")
        return _FakeScanPaginator(self._table)
