import jwt

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.auth import router
from app.services.refresh_service import (
    get_refresh_service,
)


class FakeRefreshService:

    def refresh(
        self,
        refresh_token: str,
    ) -> str:
        assert (
            refresh_token
            == "test-refresh-token"
        )

        return "test-access-token"


def test_refresh_endpoint_returns_access_token():
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_refresh_service] = (
        lambda: FakeRefreshService()
    )

    client = TestClient(app)

    response = client.post(
        "/auth/refresh",
        json={
            "refresh_token": "test-refresh-token",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "access_token": "test-access-token",
    }


def test_refresh_endpoint_returns_401_for_invalid_session():
    class FailingRefreshService:
        def refresh(
            self,
            refresh_token: str,
        ) -> str:
            raise ValueError(
                "Session has expired"
            )

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_refresh_service] = (
        lambda: FailingRefreshService()
    )

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.post(
        "/auth/refresh",
        json={
            "refresh_token": "test-refresh-token",
        },
    )

    assert response.status_code == 401


def test_refresh_endpoint_returns_401_for_invalid_token():
    class InvalidTokenRefreshService:
        def refresh(
            self,
            refresh_token: str,
        ) -> str:
            raise jwt.InvalidTokenError(
                "Invalid refresh token"
            )

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_refresh_service] = (
        lambda: InvalidTokenRefreshService()
    )

    client = TestClient(
        app,
        raise_server_exceptions=False,
    )

    response = client.post(
        "/auth/refresh",
        json={
            "refresh_token": "invalid-token",
        },
    )

    assert response.status_code == 401