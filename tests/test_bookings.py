"""Tests for the bookings CRUD endpoints."""

from fastapi.testclient import TestClient


def create_booking(client: TestClient) -> dict:
    """Helper to create a booking."""
    payload = {
        "user_id": "user-001",
        "property_id": "property-001",
        "check_in_date": "2026-09-01",
        "check_out_date": "2026-09-05",
        "guests": 2,
        "total_price": 720.0,
    }

    response = client.post("/bookings", json=payload)
    assert response.status_code == 201
    return response.json()


def test_list_bookings_empty(booking_client: TestClient) -> None:
    response = booking_client.get("/bookings")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_booking(booking_client: TestClient) -> None:
    created = create_booking(booking_client)

    response = booking_client.get(f"/bookings/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_list_bookings_after_creation(booking_client: TestClient) -> None:
    created = create_booking(booking_client)

    response = booking_client.get("/bookings")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == created["id"]


def test_update_booking_preserves_unspecified_fields(
    booking_client: TestClient,
) -> None:
    created = create_booking(booking_client)

    response = booking_client.put(
        f"/bookings/{created['id']}",
        json={
            "status": "approved",
        },
    )

    assert response.status_code == 200

    updated = response.json()

    assert updated["status"] == "approved"

    # unchanged fields
    assert updated["user_id"] == created["user_id"]
    assert updated["property_id"] == created["property_id"]
    assert updated["check_in_date"] == created["check_in_date"]
    assert updated["check_out_date"] == created["check_out_date"]
    assert updated["total_price"] == created["total_price"]


def test_delete_booking(booking_client: TestClient) -> None:
    created = create_booking(booking_client)

    response = booking_client.delete(f"/bookings/{created['id']}")

    assert response.status_code == 204

    response = booking_client.get(f"/bookings/{created['id']}")

    assert response.status_code == 404


def test_get_missing_booking_returns_404(
    booking_client: TestClient,
) -> None:
    response = booking_client.get("/bookings/does-not-exist")

    assert response.status_code == 404


def test_update_missing_booking_returns_404(
    booking_client: TestClient,
) -> None:
    response = booking_client.put(
        "/bookings/does-not-exist",
        json={"status": "approved"},
    )

    assert response.status_code == 404


def test_delete_missing_booking_returns_404(
    booking_client: TestClient,
) -> None:
    response = booking_client.delete("/bookings/does-not-exist")

    assert response.status_code == 404


def test_create_booking_validation_error(
    booking_client: TestClient,
) -> None:
    response = booking_client.post(
        "/bookings",
        json={
            "user_id": "user-001",
            "property_id": "property-001",
            "check_in_date": "2026-09-05",
            "check_out_date": "2026-09-01",
            "guests": 2,
            "total_price": 720.0,
        },
    )

    assert response.status_code == 422