from fastapi import APIRouter, Depends, status

from app.models.auth import SignupRequest, SignupResponse, VerifyOTPRequest, VerifyOTPResponse
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
    service.start_signup(str(payload.email))

    return SignupResponse(
        message="Verification code sent"
    )

@router.post(
    "/verify",
    response_model=VerifyOTPResponse,
    status_code=status.HTTP_200_OK,
)
def verify_signup(
    payload: VerifyOTPRequest,
    service: SignupService = Depends(get_signup_service),
) -> VerifyOTPResponse:
    verified = service.verify_signup_otp(
        email=str(payload.email),
        code=payload.code,
    )

    if not verified:
        return VerifyOTPResponse(
            message="Verification failed"
        )

    return VerifyOTPResponse(
        message="Account verified"
    )