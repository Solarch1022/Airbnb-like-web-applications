"""Service layer for managing items.

Business logic lives here; all persistence is delegated to the DAO layer,
which talks to DynamoDB. This keeps the service storage-agnostic and easy
to unit-test by injecting a fake/mock DAO.
"""

from __future__ import annotations

import uuid

from fastapi import Depends

from app.dao.item_dao import ItemDAO, get_item_dao
from app.models.item import Item, ItemCreate


class ItemService:
    """CRUD operations for items, backed by an ItemDAO."""

    def __init__(self, dao: ItemDAO) -> None:
        self._dao = dao

    def list_items(self) -> list[Item]:
        """Return all items."""
        return [Item(**data) for data in self._dao.list_items()]

    def get_item(self, item_id: str) -> Item | None:
        """Return a single item by id, or None if not found."""
        data = self._dao.get_item(item_id)
        return Item(**data) if data is not None else None

    def create_item(self, payload: ItemCreate) -> Item:
        """Create and persist a new item with a generated id."""
        item = Item(id=str(uuid.uuid4()), **payload.model_dump())
        self._dao.put_item(item.model_dump())
        return item

    def delete_item(self, item_id: str) -> bool:
        """Delete an item by id. Returns True if it existed."""
        return self._dao.delete_item(item_id)


def get_item_service(dao: ItemDAO = Depends(get_item_dao)) -> ItemService:
    """Dependency provider building an ItemService with the DAO injected."""
    return ItemService(dao=dao)
