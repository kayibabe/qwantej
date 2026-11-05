"""SMTP delivery for account recovery and email verification."""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _configured() -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_username))


def _deliver(to_email: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_use_ssl:
        server = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
            context=ssl.create_default_context(),
        )
    else:
        server = smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        )
    try:
        if not settings.smtp_use_ssl and settings.smtp_starttls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
    finally:
        server.quit()


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """Deliver one transactional email without blocking the event loop."""
    if not _configured():
        logger.warning("SMTP is not configured; transactional email was not sent")
        if settings.app_env != "production":
            # Development convenience: the link contains a one-time token.
            logger.info("Development email to %s: %s", to_email, body)
        return False
    try:
        await asyncio.to_thread(_deliver, to_email, subject, body)
        return True
    except Exception:
        logger.exception("Could not deliver transactional email")
        return False


async def send_password_reset_email(to_email: str, link: str) -> bool:
    return await send_email(
        to_email,
        "Reset your QwanEj password",
        (
            "Use this link to choose a new QwanEj password. It expires in "
            f"{settings.password_reset_token_minutes} minutes.\n\n{link}\n\n"
            "If you did not request this, you can ignore this message."
        ),
    )


async def send_verification_email(to_email: str, link: str) -> bool:
    return await send_email(
        to_email,
        "Verify your QwanEj email address",
        (
            "Confirm your email address for QwanEj. It expires in "
            f"{settings.email_verification_token_hours} hours.\n\n{link}\n\n"
            "If you did not create this account, you can ignore this message."
        ),
    )
