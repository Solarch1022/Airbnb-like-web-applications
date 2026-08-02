"""Business logic for bookings."""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

from fastapi import Depends

from app.dao.booking_dao import BookingDAO, get_booking_dao
from app.models.booking import Booking, BookingCreate, BookingUpdate


class BookingService:
    """Business logic for Booking CRUD."""

    def __init__(self, dao: BookingDAO):
        self._dao = dao

    def list_bookings(self) -> list[Booking]:
        """Return all bookings."""
        return [
            Booking.model_validate(booking)
            for booking in self._dao.list_bookings()
        ]

    def get_booking(
        self,
        booking_id: str,
    ) -> Booking | None:
        """Return one booking."""
        booking = self._dao.get_booking(booking_id)

        if booking is None:
            return None

        return Booking.model_validate(booking)

    def create_booking(
        self,
        booking_data: BookingCreate,
    ) -> Booking:
        """Create a booking."""
        booking = Booking(
            id=str(uuid4()),
            **booking_data.model_dump(),
        )

        self._dao.put_booking(
            booking.model_dump(mode="json"),
        )

        return booking

    def update_booking(
        self,
        booking_id: str,
        booking_update: BookingUpdate,
    ) -> Booking | None:
        """Update an existing booking."""
        existing = self._dao.get_booking(booking_id)

        if existing is None:
            return None

        updated = Booking(
            **{
                **existing,
                **booking_update.model_dump(exclude_unset=True),
            }
        )

        self._dao.update_booking(
            updated.model_dump(mode="json"),
        )

        return updated

    def delete_booking(
        self,
        booking_id: str,
    ) -> bool:
        """Delete one booking."""
        return self._dao.delete_booking(booking_id)


@lru_cache
def get_booking_service(
    dao: BookingDAO = Depends(get_booking_dao),
) -> BookingService:
    """Dependency provider."""
    return BookingService(dao)