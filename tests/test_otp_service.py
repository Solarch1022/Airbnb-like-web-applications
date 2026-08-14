from app.services.otp_service import OTPService


def test_generate_returns_six_digit_code():
    service = OTPService()

    code = service.generate()

    assert len(code) == 6
    assert code.isdigit()


def test_hash_returns_sha256_hash():
    service = OTPService()

    code_hash = service.hash("123456")

    assert len(code_hash) == 64


def test_verify_accepts_correct_code():
    service = OTPService()

    code = "123456"
    code_hash = service.hash(code)

    assert service.verify(code, code_hash) is True


def test_verify_rejects_wrong_code():
    service = OTPService()

    code_hash = service.hash("123456")

    assert service.verify("654321", code_hash) is False