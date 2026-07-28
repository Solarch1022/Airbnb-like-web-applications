"""CRUD endpoints for the User resource."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User, UserCreate, UserUpdate
from app.services.user_service import UserService, get_user_service


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[User])
def list_users(
    service: UserService = Depends(get_user_service),
) -> list[User]:
    """Return all users."""
    return service.list_users()


@router.post(
    "",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
) -> User:
    """Create a new user."""
    return service.create_user(payload)


@router.get("/{user_id}", response_model=User)
def get_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> User:
    """Return one user."""
    user = service.get_user(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return user

@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: str,
    payload: UserUpdate,
    service: UserService = Depends(get_user_service),
) -> User:
    """Update an existing user."""
    user = service.update_user(user_id, payload)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return user

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    user_id: str,
    service: UserService = Depends(get_user_service),
) -> None:
    """Delete one user."""
    if not service.delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )