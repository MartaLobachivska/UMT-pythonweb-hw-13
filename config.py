from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    VERIFY_EMAIL_EXPIRE_HOURS: int = 24
    RESET_PASSWORD_EXPIRE_MINUTES: int = 30

    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int = 587
    MAIL_SERVER: str
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    VERIFY_EMAIL_BASE_URL: str = "http://localhost:8000/auth/confirmed_email"
    RESET_PASSWORD_BASE_URL: str = "http://localhost:8000/auth/reset-password"
    REDIS_URL: str = "redis://redis:6379"
    USER_CACHE_EXPIRE_SECONDS: int = 900

    @property
    def cors_origins(self) -> list[str]:
        """Parse the comma-separated ``CORS_ORIGINS`` env var into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` instance."""
    return Settings()


settings = get_settings()