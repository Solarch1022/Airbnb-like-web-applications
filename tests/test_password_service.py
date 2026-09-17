from app.services.password_service import PasswordService


def test_hash_password_does_not_store_plaintext():
    service = PasswordService()

    password = "SecurePassword123!"
    password_hash = service.hash_password(password)

    assert password_hash != password


def test_verify_password_accepts_correct_password():
    service = PasswordService()

    password = "SecurePassword123!"
    password_hash = service.hash_password(password)

    assert service.verify_password(
        password,
        password_hash,
    ) is True


def test_verify_password_rejects_incorrect_password():
    service = PasswordService()

    password_hash = service.hash_password(
        "SecurePassword123!"
    )

    assert service.verify_password(
        "WrongPassword123!",
        password_hash,
    ) is False