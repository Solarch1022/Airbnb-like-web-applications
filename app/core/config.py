"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, populated from environment or a `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Example Python Backend"
    environment: str = "development"
    debug: bool = True

    host: str = "0.0.0.0"
    port: int = 8000

    # Comma-separated string of allowed CORS origins ("*" allows all).
    cors_origins: str = "*"

    # AWS DynamoDB
    aws_region: str = "us-east-1"
    dynamodb_table_name: str = "items"
    # Optional endpoint override (e.g. "http://localhost:8000" for DynamoDB Local).
    dynamodb_endpoint_url: str | None = None
    # Auto-create the DynamoDB table on startup if missing (local/dev only).
    auto_create_table: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
