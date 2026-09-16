from functools import lru_cache
from typing import List, cast

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    This class automatically reads variables from a .env file and validates them.
    If a variable is missing or of the wrong type, Python will catch it immediately
    before the app even starts, ensuring production safety.
    """
    # Application Config
    ENV: str = "development"

    # Secrets
    DATABASE_URL: str
    GEMINI_API_KEY: str
    FIREBASE_PROJECT_ID: str = "spanishamigo-8016a"
    FIREBASE_SERVICE_ACCOUNT_JSON: str = ""
    AUTH_ALLOW_INSECURE_DEV_TOKENS: bool = False
    LOG_LEVEL: str = "INFO"

    # Model Configuration
    GEMINI_PRIMARY_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_BACKUP_MODEL: str = "gemma-4-31b-it"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"
    # Phase 5 observes and plans but never mutates mastery. Conservative rollout
    # keeps legacy chat as the production default while allowing explicit evals.
    ADAPTIVE_V2_PLANNER_ENABLED: bool = False
    TELEMETRY_ENABLED: bool = True
    TELEMETRY_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)
    TELEMETRY_RETENTION_DAYS: int = 30

    # CORS / frontend integration
    ALLOWED_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Instructs Pydantic to read directly from a ".env" file
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def cors_origins(self) -> List[str]:
        origins = [
            origin.strip()
            for origin in self.ALLOWED_CORS_ORIGINS.split(",")
            if origin.strip()
        ]
        return list(dict.fromkeys(origins))

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.DATABASE_URL.startswith("postgres://"):
            return self.DATABASE_URL.replace(
                "postgres://",
                "postgresql+psycopg://",
                1
            )
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1
            )
        return self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return cast(Settings, Settings())
