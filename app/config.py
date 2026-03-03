import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "TOWT Planning"
    APP_VERSION: str = "2.0.0"
    APP_ENV: str = "production"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://towt_admin:towt_secure_2025@db:5432/towt_planning"

    # Security
    SECRET_KEY: str = "towt_secret_key_change_in_production_2025"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 heures

    # External URL (for portal links shared with clients/passengers)
    SITE_URL: str = "http://51.178.59.174"

    # TOWT Fleet
    FLEET: dict = {
        1: {"name": "Anemos", "code": 1},
        2: {"name": "Artemis", "code": 2},
        3: {"name": "Atlantis", "code": 3},
        4: {"name": "Atlas", "code": 4},
    }

    # Shortcut ports
    SHORTCUT_PORTS: list = ["FRFEC", "BRSSO"]

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
