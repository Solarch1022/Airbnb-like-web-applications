from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.auth import router
from app.services.login_service import get_login_service


class FakeLoginService:
    def login(
        self,
        email: str,
        password: str,
    ) -> str:
        assert email == "alice@example.com"
        assert password == "correct-password"

        return "test-refresh-token"


def test_login_endpoint_returns_refresh_token():
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_login_service] = (
        lambda: FakeLoginService()
    )

    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "refresh_token": "test-refresh-token",
    }


def test_login_endpoint_returns_401_for_invalid_credentials():
    class FailingLoginService:
        def login(
            self,
            email: str,
            password: str,
        ) -> str:
            raise ValueError("Invalid credentials")

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_login_service] = (
        lambda: FailingLoginService()
    )

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "alice@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid credentials",
    }


def test_login_endpoint_returns_422_for_invalid_email():
    class UnexpectedLoginService:
        def login(
            self,
            email: str,
            password: str,
        ) -> str:
            raise AssertionError(
                "Login service should not be called"
            )

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_login_service] = (
        lambda: UnexpectedLoginService()
    )

    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={
            "email": "not-an-email",
            "password": "some-password",
        },
    )

    assert response.status_code == 422
