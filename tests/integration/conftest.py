"""Fixtures for integration tests that run against DynamoDB Local (Docker).

These tests require the DynamoDB Local container to be running:

    docker compose up -d dynamodb-local

The endpoint defaults to http://localhost:8000 and can be overridden with the
``DYNAMODB_ENDPOINT_URL`` environment variable. If the endpoint is not
reachable, the integration tests are skipped (so the default ``pytest`` run
stays green without Docker).
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import boto3
import pytest
from fastapi.testclient import TestClient

from app.dao.item_dao import ItemDAO, get_item_dao
from app.main import create_app

ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL", "http://localhost:8000")
TABLE_NAME = "items_integration"
REGION = "us-east-1"


def _endpoint_reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8000
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(items) -> None:
    """Auto-mark every test in this package as ``integration``."""
    for item in items:
        if "tests/integration/" in item.nodeid or "tests\\integration\\" in item.nodeid:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def _require_dynamodb() -> None:
    if not _endpoint_reachable(ENDPOINT_URL):
        pytest.skip(
            f"DynamoDB Local not reachable at {ENDPOINT_URL}. "
            "Run: docker compose up -d dynamodb-local"
        )


@pytest.fixture
def ddb_client(_require_dynamodb: None):
    """Real boto3 client pointed at DynamoDB Local."""
    return boto3.client(
        "dynamodb",
        region_name=REGION,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id="local",
        aws_secret_access_key="local",
    )


@pytest.fixture
def dao(ddb_client) -> ItemDAO:
    """A real ItemDAO with a fresh, empty table for each test."""
    dao = ItemDAO(client=ddb_client, table_name=TABLE_NAME)
    # Start from a clean slate: drop the table if it lingers, then recreate.
    try:
        ddb_client.delete_table(TableName=TABLE_NAME)
        ddb_client.get_waiter("table_not_exists").wait(TableName=TABLE_NAME)
    except ddb_client.exceptions.ResourceNotFoundException:
        pass
    dao.ensure_table()
    yield dao
    # Teardown: remove the table so tests remain isolated.
    try:
        ddb_client.delete_table(TableName=TABLE_NAME)
    except ddb_client.exceptions.ResourceNotFoundException:
        pass


@pytest.fixture
def client(dao: ItemDAO) -> TestClient:
    """TestClient wired to the real DynamoDB-Local-backed DAO."""
    app = create_app()
    app.dependency_overrides[get_item_dao] = lambda: dao
    return TestClient(app)
