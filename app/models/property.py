from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class BookingMode(str, Enum):
    INSTANT = "INSTANT"
    REQUEST = "REQUEST"


class PropertyStatus(str, Enum):
    DRAFT = "DRAFT"
    ARCHIVED = "ARCHIVED"


class PropertyFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    property_type: str | None = Field(default=None, min_length=1, max_length=100)
    price_per_night: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    max_guests: int | None = Field(default=None, strict=True, ge=1, le=1000)
    images: list[HttpUrl] = Field(default_factory=list, max_length=20)
    booking_mode: BookingMode | None = None

    @field_validator("price_per_night")
    @classmethod
    def normalise_price(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.01")) if value is not None else None


class PropertyCreate(PropertyFields):
    pass


class PropertyUpdate(PropertyFields):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    images: list[HttpUrl] | None = Field(default=None, max_length=20)
    expected_version: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_patch(self):
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Provide at least one field to update")
        for name in ("title", "images"):
            if name in fields and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class Property(PropertyFields):
    property_id: str
    organisation_id: str
    created_by: str
    status: PropertyStatus
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)
    # Monotonic history guards: future publishing/booking transactions must set
    # these atomically and must never clear them when archiving/cancelling.
    published_at: datetime | None = None
    has_booking_history: bool = Field(default=False, strict=True)


class PropertyPage(BaseModel):
    items: list[Property]
    next_cursor: str | None = None
