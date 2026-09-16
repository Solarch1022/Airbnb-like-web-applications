from fastapi import APIRouter, Depends, status

from app.models.auth import (
    SignupRequest,
    SignupResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
    CompleteSignupRequest,
    CompleteSignupResponse,
)
from app.services.complete_signup_service import (
    CompleteSignupService,
    get_complete_signup_service,
)
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
    result = service.verify_signup_otp(
        email=str(payload.email),
        code=payload.code,
    )

    if not result:
        return VerifyOTPResponse(
            message="Verification failed"
        )

    if isinstance(result, str):
        return VerifyOTPResponse(
            message="Account verified",
            registration_token=result,
        )

    return VerifyOTPResponse(
        message="Account verified"
    )

@router.post(
    "/complete-signup",
    response_model=CompleteSignupResponse,
    status_code=status.HTTP_200_OK,
)
def complete_signup(
    payload: CompleteSignupRequest,
    service: CompleteSignupService = Depends(
        get_complete_signup_service
    ),
) -> CompleteSignupResponse:
    refresh_token = service.complete_signup(
        registration_token=payload.registration_token,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )

    return CompleteSignupResponse(
        message="Signup completed",
        refresh_token=refresh_token,
    )