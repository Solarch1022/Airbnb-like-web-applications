import hashlib
import secrets


class OTPService:

    def generate(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def hash(self, code: str) -> str:
        return hashlib.sha256(
            code.encode("utf-8")
        ).hexdigest()

    def verify(
        self,
        code: str,
        code_hash: str,
    ) -> bool:
        return self.hash(code) == code_hash


def get_otp_service() -> OTPService:
    return OTPService()