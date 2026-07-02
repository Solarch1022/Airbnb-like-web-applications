"""End-to-end integration tests against a real DynamoDB Local instance.

These verify behavior the in-process mocks cannot fully guarantee: real
serialization, key schema, conditional deletes, and scan semantics.
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_create_get_list_delete_roundtrip(client: TestClient) -> None:
    # Create
    payload = {"name": "Integration Widget", "description": "real DDB", "price": 12.50}
    create_resp = client.post("/items", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    item_id = created["id"]
    assert item_id

    # Get
    get_resp = client.get(f"/items/{item_id}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created

    # List
    list_resp = client.get("/items")
    assert list_resp.status_code == 200
    assert any(i["id"] == item_id for i in list_resp.json())

    # Delete
    del_resp = client.delete(f"/items/{item_id}")
    assert del_resp.status_code == 204

    # Confirm gone
    assert client.get(f"/items/{item_id}").status_code == 404


def test_delete_missing_returns_404(client: TestClient) -> None:
    # Real conditional-delete path (ConditionalCheckFailedException).
    assert client.delete("/items/nope").status_code == 404


def test_price_decimal_roundtrip(client: TestClient) -> None:
    # Ensures float -> Decimal -> stored -> read back matches through real DDB.
    resp = client.post("/items", json={"name": "Precise", "price": 3.14})
    assert resp.status_code == 201
    item_id = resp.json()["id"]
    assert client.get(f"/items/{item_id}").json()["price"] == 3.14
