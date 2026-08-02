"""Schemas for the Booking resource."""

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class BookingStatus(str, Enum):
    """Supported booking statuses."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class BookingBase(BaseModel):
    """Shared fields for a booking."""

    user_id: str = Field(..., min_length=1)
    property_id: str = Field(..., min_length=1)

    check_in_date: date
    check_out_date: date

    guests: int = Field(..., ge=1)
    total_price: float = Field(..., ge=0)

    status: BookingStatus = BookingStatus.PENDING

    @model_validator(mode="after")
    def validate_dates(self) -> "BookingBase":
        """Ensure check-out is later than check-in."""
        if self.check_out_date <= self.check_in_date:
            raise ValueError(
                "check_out_date must be later than check_in_date"
            )
        return self


class BookingCreate(BookingBase):
    """Payload used to create a booking."""


class BookingUpdate(BaseModel):
    """Payload used to partially update a booking."""

    user_id: str | None = Field(default=None, min_length=1)
    property_id: str | None = Field(default=None, min_length=1)

    check_in_date: date | None = None
    check_out_date: date | None = None

    guests: int | None = Field(default=None, ge=1)
    total_price: float | None = Field(default=None, ge=0)

    status: BookingStatus | None = None


class Booking(BookingBase):
    """A booking as returned by the API."""

    id: str