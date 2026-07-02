"""Unit tests for the DynamoDB DAO using a mocked boto3 client."""

from decimal import Decimal
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.dao.item_dao import ItemDAO, _from_dynamodb_item, _to_dynamodb_item


def test_serialize_roundtrip() -> None:
    original = {"id": "abc", "name": "Widget", "description": None, "price": 9.99}
    ddb = _to_dynamodb_item(original)

    # None values are dropped; floats become Decimal-backed "N" attributes.
    assert "description" not in ddb
    assert ddb["id"] == {"S": "abc"}
    assert ddb["price"] == {"N": "9.99"}

    restored = _from_dynamodb_item(ddb)
    assert restored == {"id": "abc", "name": "Widget", "price": 9.99}


def test_get_item_returns_none_when_absent() -> None:
    client = MagicMock()
    client.get_item.return_value = {}
    dao = ItemDAO(client=client, table_name="items")

    assert dao.get_item("missing") is None
    client.get_item.assert_called_once_with(
        TableName="items", Key={"id": {"S": "missing"}}
    )


def test_get_item_deserializes() -> None:
    client = MagicMock()
    client.get_item.return_value = {
        "Item": {"id": {"S": "x1"}, "name": {"S": "Gadget"}, "price": {"N": "5"}}
    }
    dao = ItemDAO(client=client, table_name="items")

    assert dao.get_item("x1") == {"id": "x1", "name": "Gadget", "price": 5}


def test_put_item_serializes_payload() -> None:
    client = MagicMock()
    dao = ItemDAO(client=client, table_name="items")

    item = {"id": "x1", "name": "Gadget", "price": 5.0}
    assert dao.put_item(item) == item
    _, kwargs = client.put_item.call_args
    assert kwargs["TableName"] == "items"
    assert kwargs["Item"]["price"] == {"N": "5.0"}


def test_delete_item_true_when_existed() -> None:
    client = MagicMock()
    client.delete_item.return_value = {"Attributes": {"id": {"S": "x1"}}}
    dao = ItemDAO(client=client, table_name="items")

    assert dao.delete_item("x1") is True


def test_delete_item_false_on_conditional_failure() -> None:
    client = MagicMock()
    client.delete_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "no"}},
        "DeleteItem",
    )
    dao = ItemDAO(client=client, table_name="items")

    assert dao.delete_item("missing") is False


def test_list_items_paginates() -> None:
    client = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"Items": [{"id": {"S": "a"}, "name": {"S": "A"}, "price": {"N": "1"}}]},
        {"Items": [{"id": {"S": "b"}, "name": {"S": "B"}, "price": {"N": "2"}}]},
    ]
    client.get_paginator.return_value = paginator
    dao = ItemDAO(client=client, table_name="items")

    items = dao.list_items()
    assert [i["id"] for i in items] == ["a", "b"]
