"""Service layer for managing properties."""

from __future__ import annotations

import uuid

from fastapi import Depends

from app.dao.property_dao import PropertyDAO, get_property_dao
from app.models.property import Property, PropertyCreate, PropertyUpdate


class PropertyService:
    """CRUD operations for properties."""

    def __init__(self, dao: PropertyDAO) -> None:
        self._dao = dao

    def list_properties(self) -> list[Property]:
        """Return all properties."""
        return [
            Property(**data)
            for data in self._dao.list_properties()
        ]

    def get_property(
        self,
        property_id: str,
    ) -> Property | None:
        """Return one property by id."""
        data = self._dao.get_property(property_id)
        return Property(**data) if data is not None else None

    def create_property(
        self,
        payload: PropertyCreate,
    ) -> Property:
        """Create and persist a new property."""
        property_record = Property(
            id=str(uuid.uuid4()),
            **payload.model_dump(),
        )

        self._dao.put_property(
            property_record.model_dump(),
        )

        return property_record

    def update_property(
        self,
        property_id: str,
        payload: PropertyUpdate,
    ) -> Property | None:
        """Partially update an existing property."""
        existing_property = self._dao.get_property(property_id)

        if existing_property is None:
            return None

        update_data = payload.model_dump(exclude_unset=True)

        updated_data = {
            **existing_property,
            **update_data,
            "id": property_id,
        }

        updated_property = Property(**updated_data)

        self._dao.update_property(
            updated_property.model_dump(),
        )

        return updated_property

    def delete_property(self, property_id: str) -> bool:
        """Delete a property by id."""
        return self._dao.delete_property(property_id)


def get_property_service(
    dao: PropertyDAO = Depends(get_property_dao),
) -> PropertyService:
    """Dependency provider for PropertyService."""
    return PropertyService(dao=dao)