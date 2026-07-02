"""Focused example: creating an item through the API down to the DynamoDB client.

Unlike ``test_items.py`` (which uses a fake DAO), these tests use the *real*
``ItemDAO`` on top of a mocked boto3 DynamoDB client, so the full create path
- router -> service -> DAO -> boto3 ``put_item`` - is verified, including the
attribute-value serialization.
"""

from fastapi.testclient import TestClient

from app.dao.item_dao import ItemDAO
from app.models.item import ItemCreate
from tests.mocks import FakeDynamoDBClient


def test_create_item_calls_ddb_put_item(
    client_with_ddb_mock: TestClient,
    ddb_client: FakeDynamoDBClient,
) -> None:
    """POST /items should persist a correctly-serialized item via put_item."""
    payload = {"name": "Widget", "description": "A useful widget", "price": 9.99}

    response = client_with_ddb_mock.post("/items", json=payload)

    assert response.status_code == 201
    created = response.json()
    assert created["id"]  # a UUID string was generated
    assert created["name"] == "Widget"

    # The DAO called the boto3 client's put_item exactly once...
    put_calls = [c for c in ddb_client.calls if c[0] == "put_item"]
    assert len(put_calls) == 1

    # ...with the item serialized into DynamoDB attribute-value format.
    _, kwargs = put_calls[0]
    assert kwargs["TableName"] == "items"
    stored = kwargs["Item"]
    assert stored["id"] == {"S": created["id"]}
    assert stored["name"] == {"S": "Widget"}
    assert stored["price"] == {"N": "9.99"}  # float -> Decimal -> "N"

    # And the created item is immediately retrievable through the same client.
    get_resp = client_with_ddb_mock.get(f"/items/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


def test_dao_create_directly_with_mock_client() -> None:
    """Unit-level example: use ItemDAO with the fake client, no HTTP layer."""
    ddb_client = FakeDynamoDBClient()
    dao = ItemDAO(client=ddb_client, table_name="items")

    payload = ItemCreate(name="Gadget", price=5.0)
    item = {"id": "fixed-id", **payload.model_dump()}

    dao.put_item(item)

    # description is None, so it is not stored; price 5.0 round-trips as int 5.
    fetched = dao.get_item("fixed-id")
    assert fetched == {"id": "fixed-id", "name": "Gadget", "price": 5}
