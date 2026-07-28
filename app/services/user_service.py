"""Service layer for managing users."""

from __future__ import annotations

import uuid

from fastapi import Depends

from app.dao.user_dao import UserDAO, get_user_dao
from app.models.user import User, UserCreate


class UserService:
    """CRUD operations for users."""

    def __init__(self, dao: UserDAO) -> None:
        self._dao = dao

    def list_users(self) -> list[User]:
        """Return all users."""
        return [User(**data) for data in self._dao.list_users()]

    def get_user(self, user_id: str) -> User | None:
        """Return one user."""
        data = self._dao.get_user(user_id)
        return User(**data) if data else None

    def create_user(self, payload: UserCreate) -> User:
        """Create a new user."""
        user = User(
            id=str(uuid.uuid4()),
            **payload.model_dump(),
        )

        self._dao.put_user(user.model_dump())

        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        return self._dao.delete_user(user_id)


def get_user_service(
    dao: UserDAO = Depends(get_user_dao),
) -> UserService:
    """Dependency provider."""
    return UserService(dao)