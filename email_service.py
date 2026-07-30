from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from config import settings
from security import create_email_token


mail_config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
)


async def send_verification_email(email: str, username: str) -> None:
    token = create_email_token({"sub": email})
    verify_url = f"{settings.VERIFY_EMAIL_BASE_URL}?token={token}"
    html = (
        f"<h3>Вітаємо, {username}!</h3>"
        f"<p>Підтвердіть email: <a href='{verify_url}'>Підтвердити адресу</a></p>"
    )
    message = MessageSchema(
        subject="Підтвердження email",
        recipients=[email],
        body=html,
        subtype=MessageType.html,
    )
    await FastMail(mail_config).send_message(message)
