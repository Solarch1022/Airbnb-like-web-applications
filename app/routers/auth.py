"""Authentication and onboarding endpoints."""

from fastapi import APIRouter, Depends, status

from app.models.auth import SignupRequest, SignupResponse
from app.services.signup_service import SignupService, get_signup_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_200_OK,
)
def signup(
    payload: SignupRequest,
    service: SignupService = Depends(get_signup_service),
) -> SignupResponse:
    """Start signup by sending an email verification code."""
    service.start_signup(str(payload.email))

    return SignupResponse(
        message="Verification code sent"
    )