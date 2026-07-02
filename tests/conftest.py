"""Shared pytest fixtures.

Two client fixtures are provided:

* ``client`` - wired to an in-memory ``FakeItemDAO`` (fast; skips boto3 entirely).
* ``client_with_ddb_mock`` - wired to the *real* ``ItemDAO`` backed by a
  ``FakeDynamoDBClient``, so the boto3 serialization path is exercised without AWS.

Both avoid any real AWS/DynamoDB connection.
"""

import pytest
from fastapi.testclient import TestClient

from app.dao.item_dao import ItemDAO, get_item_dao
from app.main import create_app
from tests.mocks import FakeDynamoDBClient, FakeItemDAO


@pytest.fixture
def client() -> TestClient:
    """Return a TestClient wired to a fresh in-memory fake DAO."""
    app = create_app()
    fake_dao = FakeItemDAO()
    app.dependency_overrides[get_item_dao] = lambda: fake_dao
    return TestClient(app)


@pytest.fixture
def ddb_client() -> FakeDynamoDBClient:
    """Return a fresh fake low-level DynamoDB client."""
    return FakeDynamoDBClient()


@pytest.fixture
def client_with_ddb_mock(ddb_client: FakeDynamoDBClient) -> TestClient:
    """TestClient using the real ItemDAO on top of a mocked boto3 client.

    This exercises the DAO's attribute-value serialization end-to-end.
    """
    app = create_app()
    dao = ItemDAO(client=ddb_client, table_name="items")
    app.dependency_overrides[get_item_dao] = lambda: dao
    return TestClient(app)
