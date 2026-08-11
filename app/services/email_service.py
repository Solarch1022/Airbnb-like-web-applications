"""Email delivery abstraction used by onboarding flows."""


class EmailService:
    """Service responsible for sending onboarding emails."""

    def send_verification_code(
        self,
        email: str,
        code: str,
    ) -> None:
        """Send an email verification code."""
        raise NotImplementedError


class ConsoleEmailService(EmailService):
    """Development email service that prints codes to the console."""

    def send_verification_code(
        self,
        email: str,
        code: str,
    ) -> None:
        print(f"[EMAIL] Verification code for {email}: {code}")


def get_email_service() -> EmailService:
    """Return the email service used by the application."""
    return ConsoleEmailService()