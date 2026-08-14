from __future__ import annotations


class EmailService:

    def send_verification_code(
        self,
        email: str,
        code: str,
    ) -> None:
        raise NotImplementedError


class ConsoleEmailService(EmailService):

    # TODO: Replace with a production email provider before deployment.
    def send_verification_code(
        self,
        email: str,
        code: str,
    ) -> None:
        print(
            f"[EMAIL] Verification code for {email}: {code}"
        )


def get_email_service() -> EmailService:
    return ConsoleEmailService()