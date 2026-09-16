from pwdlib import PasswordHash
from functools import lru_cache

class PasswordService:

    def __init__(self) -> None:
        self._password_hash = PasswordHash.recommended()

    def hash_password(
        self,
        password: str,
    ) -> str:
        return self._password_hash.hash(password)

    def verify_password(
        self,
        password: str,
        password_hash: str,
    ) -> bool:
        return self._password_hash.verify(
            password,
            password_hash,
        )

@lru_cache
def get_password_service() -> PasswordService:
    return PasswordService()