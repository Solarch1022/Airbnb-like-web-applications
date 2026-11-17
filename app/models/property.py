from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class BookingMode(str, Enum):
    INSTANT = "INSTANT"
    REQUEST = "REQUEST"


class PropertyStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
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
    public_location: str | None = Field(default=None, min_length=1, max_length=200)
    min_nights: int | None = Field(default=None, strict=True, ge=1, le=90)
    max_nights: int | None = Field(default=None, strict=True, ge=1, le=90)
    preparation_nights: int | None = Field(default=None, strict=True, ge=0, le=7)
    blocked_dates: list[date] = Field(default_factory=list, max_length=366)

    @field_validator("blocked_dates", mode="before")
    @classmethod
    def require_calendar_dates(cls, value):
        if isinstance(value, list):
            for item in value:
                if type(item) is not date and not (isinstance(item, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", item)):
                    raise ValueError("Blocked dates must use YYYY-MM-DD calendar dates")
        return value

    @field_validator("blocked_dates")
    @classmethod
    def validate_blocked_dates(cls, value: list[date] | None) -> list[date] | None:
        if value is None:
            return value
        if len(value) != len(set(value)):
            raise ValueError("Blocked dates must be unique")
        return sorted(value)

    @model_validator(mode="after")
    def validate_stay_limits(self):
        if self.min_nights is not None and self.max_nights is not None and self.max_nights < self.min_nights:
            raise ValueError("Maximum nights must be at least minimum nights")
        return self

    @field_validator("price_per_night")
    @classmethod
    def normalise_price(cls, value: Decimal | None) -> Decimal | None:
        return value.quantize(Decimal("0.01")) if value is not None else None


class PropertyCreate(PropertyFields):
    pass


class PropertyUpdate(PropertyFields):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    images: list[HttpUrl] | None = Field(default=None, max_length=20)
    blocked_dates: list[date] | None = Field(default=None, max_length=366)
    expected_version: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_patch(self):
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Provide at least one field to update")
        for name in ("title", "images", "blocked_dates"):
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



class PropertyVersionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(strict=True, ge=1)


class ReadinessIssue(BaseModel):
    field: str
    message: str


class PropertyReadiness(BaseModel):
    ready: bool
    can_publish: bool
    version: int
    status: PropertyStatus
    issues: list[ReadinessIssue]


class PublicProperty(BaseModel):
    property_id: str
    title: str
    description: str
    public_location: str
    property_type: str
    price_per_night: Decimal
    currency: str
    max_guests: int
    images: list[HttpUrl]
    booking_mode: BookingMode
    min_nights: int
    max_nights: int


class PublicPropertyPage(BaseModel):
    items: list[PublicProperty]
    next_cursor: str | None = None
