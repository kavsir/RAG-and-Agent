from src.config.settings import settings


class EmailConfig:
    EMAIL_ENABLED = settings.EMAIL_ENABLED
    SENDER_EMAIL = settings.SMTP_USER
    APP_PASSWORD = settings.SMTP_PASSWORD
    SMTP_SERVER = settings.SMTP_HOST
    SMTP_PORT = settings.SMTP_PORT
