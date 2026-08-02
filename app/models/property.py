"""Schemas for the Property resource."""

from enum import Enum

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    """Supported property types."""

    HOUSE = "house"
    APARTMENT = "apartment"
    UNIT = "unit"
    TOWNHOUSE = "townhouse"
    VILLA = "villa"
    OTHER = "other"


class PropertyStatus(str, Enum):
    """Availability status of a property."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class PropertyBase(BaseModel):
    """Shared fields for a property."""

    owner_id: str = Field(..., min_length=1)

    title: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)

    property_type: PropertyType

    address: str = Field(..., min_length=1, max_length=250)
    suburb: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=50)
    postcode: str = Field(..., min_length=4, max_length=10)

    bedrooms: int = Field(..., ge=0)
    bathrooms: int = Field(..., ge=0)
    max_guests: int = Field(..., ge=1)

    price_per_night: float = Field(..., ge=0)

    status: PropertyStatus = PropertyStatus.AVAILABLE
    amenities: list[str] = Field(default_factory=list)


class PropertyCreate(PropertyBase):
    """Payload used to create a property."""


class PropertyUpdate(BaseModel):
    """Payload used to partially update a property."""

    owner_id: str | None = Field(default=None, min_length=1)

    title: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)

    property_type: PropertyType | None = None

    address: str | None = Field(default=None, min_length=1, max_length=250)
    suburb: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=50)
    postcode: str | None = Field(default=None, min_length=4, max_length=10)

    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    max_guests: int | None = Field(default=None, ge=1)

    price_per_night: float | None = Field(default=None, ge=0)

    status: PropertyStatus | None = None
    amenities: list[str] | None = None


class Property(PropertyBase):
    """A property as returned by the API."""

    id: str