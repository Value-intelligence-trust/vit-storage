import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Centralized Configuration Settings for Tachyon Fabric.
    Loads and validates environment configurations using Pydantic Settings.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PORT: int = 8080
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "sqlite+aiosqlite:///./tachyon.db"
    REDIS_URL: Optional[str] = None

    # Google Drive Settings
    GDRIVE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    GDRIVE_SERVICE_ACCOUNT_KEYS: Optional[str] = "[]"

    # Microsoft OneDrive Settings
    ONEDRIVE_CLIENT_ID: Optional[str] = None
    ONEDRIVE_CLIENT_SECRET: Optional[str] = None
    ONEDRIVE_TENANT_ID: str = "common"

    # Dropbox Settings
    DROPBOX_APP_KEY: Optional[str] = None
    DROPBOX_APP_SECRET: Optional[str] = None
    DROPBOX_ACCESS_TOKEN: Optional[str] = None
    DROPBOX_REFRESH_TOKEN: Optional[str] = None

    # S3 Compatible Settings
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    S3_REGION: str = "us-east-1"

    # VIT Chain integration (Chain ID 7764)
    VIT_SWARM_COORDINATOR_ADDRESS: Optional[str] = None

    # Platform Variables
    TACHYON_MAX_FILE_SIZE_MB: int = 100
    TACHYON_DATA_SHARDS: int = 6
    TACHYON_PARITY_SHARDS: int = 3
    TACHYON_STORAGE_PATH: str = "/tmp/tachyon_storage"
    VIT_STORAGE_USE_EXTERNAL: bool = False

# Instantiate settings singleton
settings = Settings()

# --- Backwards Compatibility Helpers ---

def get_env(name: str, default: str = "") -> str:
    """Helper used to resolve setting with environment variables override."""
    if hasattr(settings, name):
        val = getattr(settings, name)
        return str(val) if val is not None else default
    return os.getenv(name, default)

def get_int_env(name: str, default: str = "0") -> int:
    """Helper used to resolve integer configuration with fallback."""
    try:
        if hasattr(settings, name):
            val = getattr(settings, name)
            return int(val) if val is not None else int(default)
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)
