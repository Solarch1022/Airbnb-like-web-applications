"""CRUD endpoints for the example Item resource."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.item import Item, ItemCreate
from app.services.item_service import ItemService, get_item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[Item])
def list_items(service: ItemService = Depends(get_item_service)) -> list[Item]:
    """Return all items."""
    return service.list_items()


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(
    payload: ItemCreate,
    service: ItemService = Depends(get_item_service),
) -> Item:
    """Create a new item."""
    return service.create_item(payload)


@router.get("/{item_id}", response_model=Item)
def get_item(
    item_id: str,
    service: ItemService = Depends(get_item_service),
) -> Item:
    """Return a single item by id."""
    item = service.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    service: ItemService = Depends(get_item_service),
) -> None:
    """Delete an item by id."""
    if not service.delete_item(item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} not found",
        )
