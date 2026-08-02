"""Tests for the properties CRUD endpoints."""

from fastapi.testclient import TestClient


VALID_PROPERTY = {
    "owner_id": "owner-001",
    "title": "Modern Apartment in Perth",
    "description": "A comfortable apartment close to the city.",
    "property_type": "apartment",
    "address": "10 Example Street",
    "suburb": "Perth",
    "state": "WA",
    "postcode": "6000",
    "bedrooms": 2,
    "bathrooms": 1,
    "max_guests": 4,
    "price_per_night": 180.0,
    "status": "available",
    "amenities": ["wifi", "parking"],
}


def test_list_properties_empty(client: TestClient) -> None:
    response = client.get("/properties")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_property(client: TestClient) -> None:
    create_response = client.post(
        "/properties",
        json=VALID_PROPERTY,
    )

    assert create_response.status_code == 201

    created = create_response.json()

    assert isinstance(created["id"], str)
    assert created["id"]
    assert created["owner_id"] == "owner-001"
    assert created["title"] == "Modern Apartment in Perth"
    assert created["property_type"] == "apartment"
    assert created["price_per_night"] == 180.0
    assert created["status"] == "available"

    get_response = client.get(
        f"/properties/{created['id']}",
    )

    assert get_response.status_code == 200
    assert get_response.json() == created


def test_list_properties_after_creation(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/properties",
        json=VALID_PROPERTY,
    )
    created = create_response.json()

    list_response = client.get("/properties")

    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_update_property_preserves_unspecified_fields(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/properties",
        json=VALID_PROPERTY,
    )
    created = create_response.json()
    property_id = created["id"]

    update_response = client.put(
        f"/properties/{property_id}",
        json={"price_per_night": 220.0},
    )

    assert update_response.status_code == 200

    updated = update_response.json()

    assert updated["id"] == property_id
    assert updated["price_per_night"] == 220.0

    assert updated["owner_id"] == created["owner_id"]
    assert updated["title"] == created["title"]
    assert updated["description"] == created["description"]
    assert updated["property_type"] == created["property_type"]
    assert updated["address"] == created["address"]
    assert updated["suburb"] == created["suburb"]
    assert updated["state"] == created["state"]
    assert updated["postcode"] == created["postcode"]
    assert updated["bedrooms"] == created["bedrooms"]
    assert updated["bathrooms"] == created["bathrooms"]
    assert updated["max_guests"] == created["max_guests"]
    assert updated["status"] == created["status"]
    assert updated["amenities"] == created["amenities"]

    get_response = client.get(
        f"/properties/{property_id}",
    )

    assert get_response.status_code == 200
    assert get_response.json() == updated


def test_delete_property(client: TestClient) -> None:
    create_response = client.post(
        "/properties",
        json=VALID_PROPERTY,
    )
    property_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/properties/{property_id}",
    )

    assert delete_response.status_code == 204

    get_response = client.get(
        f"/properties/{property_id}",
    )

    assert get_response.status_code == 404


def test_get_missing_property_returns_404(
    client: TestClient,
) -> None:
    response = client.get(
        "/properties/does-not-exist",
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Property does-not-exist not found"
    }


def test_update_missing_property_returns_404(
    client: TestClient,
) -> None:
    response = client.put(
        "/properties/does-not-exist",
        json={"title": "Updated Property"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Property does-not-exist not found"
    }


def test_delete_missing_property_returns_404(
    client: TestClient,
) -> None:
    response = client.delete(
        "/properties/does-not-exist",
    )

    assert response.status_code == 404


def test_create_property_validation_error(
    client: TestClient,
) -> None:
    invalid_payload = {
        **VALID_PROPERTY,
        "price_per_night": -1,
    }

    response = client.post(
        "/properties",
        json=invalid_payload,
    )

    assert response.status_code == 422