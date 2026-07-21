from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://app_user:change-me@postgres.example.internal:5432/app_db"
    )
    public_base_url: AnyHttpUrl = "https://mcp.example.com"
    meo_base_url: AnyHttpUrl = "https://app.example.com"
    meo_connector_api_key: str = ""
    meo_connector_hmac_secret: str = ""
    token_encryption_key: str = ""
    allowed_origins: list[str] = Field(default_factory=list)
    log_level: str = "INFO"

    @property
    def issuer(self) -> str:
        return str(self.public_base_url).rstrip("/")

    @property
    def resource(self) -> str:
        return f"{self.issuer}/mcp"


@lru_cache
def get_settings() -> Settings:
    return Settings()
