"""Schemas for the example Item resource."""

from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    """Shared fields for an item."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    price: float = Field(..., ge=0)


class ItemCreate(ItemBase):
    """Payload used to create an item."""


class Item(ItemBase):
    """An item as returned by the API."""

    id: str
