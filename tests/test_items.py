"""Tests for the items CRUD endpoints."""

from fastapi.testclient import TestClient


def test_list_items_empty(client: TestClient) -> None:
    response = client.get("/items")
    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_item(client: TestClient) -> None:
    payload = {"name": "Widget", "description": "A useful widget", "price": 9.99}
    create_resp = client.post("/items", json=payload)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert isinstance(created["id"], str) and created["id"]
    assert created["name"] == "Widget"

    get_resp = client.get(f"/items/{created['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == created


def test_get_missing_item_returns_404(client: TestClient) -> None:
    response = client.get("/items/does-not-exist")
    assert response.status_code == 404


def test_create_item_validation_error(client: TestClient) -> None:
    # Negative price violates the ge=0 constraint.
    response = client.post("/items", json={"name": "Bad", "price": -1})
    assert response.status_code == 422


def test_delete_item(client: TestClient) -> None:
    create_resp = client.post("/items", json={"name": "Temp", "price": 1.0})
    item_id = create_resp.json()["id"]

    delete_resp = client.delete(f"/items/{item_id}")
    assert delete_resp.status_code == 204

    assert client.get(f"/items/{item_id}").status_code == 404


def test_delete_missing_item_returns_404(client: TestClient) -> None:
    assert client.delete("/items/does-not-exist").status_code == 404
