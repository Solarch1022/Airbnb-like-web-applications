"""Runnable example: create an item via the DAO and the AWS DynamoDB client.

This shows the create path the API uses (service -> DAO -> boto3 DynamoDB
client) as a standalone script. It can run in two modes:

1. MOCK mode (default) - uses the in-memory ``FakeDynamoDBClient`` from the test
   suite, so it runs anywhere with no AWS access. Great for demos/CI.

2. REAL mode - talks to an actual DynamoDB endpoint (real AWS or DynamoDB Local)
   via boto3, using the app settings (AWS_REGION, DYNAMODB_TABLE_NAME,
   DYNAMODB_ENDPOINT_URL).

Usage:

    # Mocked, no AWS needed:
    python -m examples.create_item_example

    # Against DynamoDB Local (see README for how to start it + create the table):
    DYNAMODB_ENDPOINT_URL=http://localhost:8000 \\
        python -m examples.create_item_example --real
"""

from __future__ import annotations

import argparse
import uuid

from app.dao.item_dao import ItemDAO
from app.models.item import Item, ItemCreate
from app.services.item_service import ItemService


def build_service(*, real: bool) -> ItemService:
    """Construct an ItemService backed by either a real or mocked DDB client."""
    if real:
        # Reuse the app's configured, cached DynamoDB-backed DAO.
        from app.dao.item_dao import get_item_dao

        dao = get_item_dao()
        print("[mode] REAL - using boto3 DynamoDB client from app settings")
    else:
        # Import lazily so the example has no hard dependency on test code
        # unless mock mode is actually used.
        from tests.mocks import FakeDynamoDBClient

        dao = ItemDAO(client=FakeDynamoDBClient(), table_name="items")
        print("[mode] MOCK - using in-memory FakeDynamoDBClient (no AWS)")
    return ItemService(dao=dao)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--real",
        action="store_true",
        help="Talk to a real DynamoDB endpoint instead of the in-memory mock.",
    )
    args = parser.parse_args()

    service = build_service(real=args.real)

    # 1) Build the create payload (same schema the API validates).
    payload = ItemCreate(name="Example Widget", description="Created by example", price=19.99)
    print(f"\nCreating item: {payload.model_dump()}")

    # 2) Create it. Under the hood this generates a UUID id, serializes the
    #    item to DynamoDB attribute-value format, and calls put_item.
    created: Item = service.create_item(payload)
    print(f"Created -> id={created.id}")

    # 3) Read it back through the same client to confirm it persisted.
    fetched = service.get_item(created.id)
    print(f"Fetched -> {fetched.model_dump() if fetched else None}")

    # 4) List all items.
    all_items = service.list_items()
    print(f"Table now has {len(all_items)} item(s).")


if __name__ == "__main__":
    main()
