"""CRUD endpoints for the Booking resource."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.booking import Booking, BookingCreate, BookingUpdate
from app.services.booking_service import BookingService, get_booking_service


router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("", response_model=list[Booking])
def list_bookings(
    service: BookingService = Depends(get_booking_service),
) -> list[Booking]:
    """Return all bookings."""
    return service.list_bookings()


@router.post(
    "",
    response_model=Booking,
    status_code=status.HTTP_201_CREATED,
)
def create_booking(
    payload: BookingCreate,
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Create a new booking."""
    return service.create_booking(payload)


@router.get("/{booking_id}", response_model=Booking)
def get_booking(
    booking_id: str,
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Return one booking by id."""
    booking = service.get_booking(booking_id)

    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )

    return booking


@router.put("/{booking_id}", response_model=Booking)
def update_booking(
    booking_id: str,
    payload: BookingUpdate,
    service: BookingService = Depends(get_booking_service),
) -> Booking:
    """Update an existing booking."""
    booking = service.update_booking(booking_id, payload)

    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )

    return booking


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_booking(
    booking_id: str,
    service: BookingService = Depends(get_booking_service),
) -> None:
    """Delete one booking."""
    if not service.delete_booking(booking_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )