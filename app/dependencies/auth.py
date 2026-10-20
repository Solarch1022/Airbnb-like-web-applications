import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.auth import CurrentUser
from app.services.authentication_service import (
    AuthenticationError,
    AuthenticationService,
    get_authentication_service,
)


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    service: AuthenticationService = Depends(
        get_authentication_service
    ),
) -> CurrentUser:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise error

    try:
        return service.authenticate(credentials.credentials)
    except (AuthenticationError, jwt.InvalidTokenError) as exc:
        raise error from exc
