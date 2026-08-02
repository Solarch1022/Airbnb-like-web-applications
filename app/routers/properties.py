"""CRUD endpoints for the Property resource."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.property import Property, PropertyCreate, PropertyUpdate
from app.services.property_service import (
    PropertyService,
    get_property_service,
)


router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=list[Property])
def list_properties(
    service: PropertyService = Depends(get_property_service),
) -> list[Property]:
    """Return all properties."""
    return service.list_properties()


@router.post(
    "",
    response_model=Property,
    status_code=status.HTTP_201_CREATED,
)
def create_property(
    payload: PropertyCreate,
    service: PropertyService = Depends(get_property_service),
) -> Property:
    """Create a new property."""
    return service.create_property(payload)


@router.get("/{property_id}", response_model=Property)
def get_property(
    property_id: str,
    service: PropertyService = Depends(get_property_service),
) -> Property:
    """Return one property by id."""
    property_record = service.get_property(property_id)

    if property_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found",
        )

    return property_record


@router.put("/{property_id}", response_model=Property)
def update_property(
    property_id: str,
    payload: PropertyUpdate,
    service: PropertyService = Depends(get_property_service),
) -> Property:
    """Update an existing property."""
    property_record = service.update_property(property_id, payload)

    if property_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found",
        )

    return property_record


@router.delete(
    "/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_property(
    property_id: str,
    service: PropertyService = Depends(get_property_service),
) -> None:
    """Delete one property."""
    if not service.delete_property(property_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found",
        )