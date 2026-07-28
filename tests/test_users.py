"""Tests for the users CRUD endpoints."""

from fastapi.testclient import TestClient


VALID_USER = {
    "name": "Thomas",
    "email_info": [
        {
            "email": "thomas@student.uwa.edu.au",
            "is_verified": True,
        }
    ],
    "phone": "0412345678",
    "credential_id": "cred001",
    "type": "owner",
}


def test_list_users_empty(client: TestClient) -> None:
    response = client.get("/users")

    assert response.status_code == 200
    assert response.json() == []


def test_create_and_get_user(client: TestClient) -> None:
    create_response = client.post("/users", json=VALID_USER)

    assert create_response.status_code == 201

    created = create_response.json()

    assert isinstance(created["id"], str)
    assert created["id"]
    assert created["name"] == "Thomas"
    assert created["phone"] == "0412345678"
    assert created["type"] == "owner"

    get_response = client.get(f"/users/{created['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == created


def test_list_users_after_creation(client: TestClient) -> None:
    create_response = client.post("/users", json=VALID_USER)
    created = create_response.json()

    list_response = client.get("/users")

    assert list_response.status_code == 200
    assert list_response.json() == [created]


def test_update_user_preserves_unspecified_fields(
    client: TestClient,
) -> None:
    create_response = client.post("/users", json=VALID_USER)
    created = create_response.json()
    user_id = created["id"]

    update_response = client.put(
        f"/users/{user_id}",
        json={"phone": "0400000000"},
    )

    assert update_response.status_code == 200

    updated = update_response.json()

    assert updated["id"] == user_id
    assert updated["phone"] == "0400000000"
    assert updated["name"] == created["name"]
    assert updated["email_info"] == created["email_info"]
    assert updated["credential_id"] == created["credential_id"]
    assert updated["type"] == created["type"]

    get_response = client.get(f"/users/{user_id}")

    assert get_response.status_code == 200
    assert get_response.json() == updated


def test_delete_user(client: TestClient) -> None:
    create_response = client.post("/users", json=VALID_USER)
    user_id = create_response.json()["id"]

    delete_response = client.delete(f"/users/{user_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/users/{user_id}").status_code == 404


def test_get_missing_user_returns_404(client: TestClient) -> None:
    response = client.get("/users/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User does-not-exist not found"
    }


def test_update_missing_user_returns_404(
    client: TestClient,
) -> None:
    response = client.put(
        "/users/does-not-exist",
        json={"name": "Updated User"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "User does-not-exist not found"
    }


def test_delete_missing_user_returns_404(
    client: TestClient,
) -> None:
    response = client.delete("/users/does-not-exist")

    assert response.status_code == 404


def test_create_user_validation_error(
    client: TestClient,
) -> None:
    invalid_payload = {
        "name": "Invalid User",
        "email_info": [],
        "phone": "0412345678",
        "credential_id": "cred001",
        "type": "invalid-type",
    }

    response = client.post("/users", json=invalid_payload)

    assert response.status_code == 422