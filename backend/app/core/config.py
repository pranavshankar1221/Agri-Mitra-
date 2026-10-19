from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_URL = (
    f"sqlite:///{(PROJECT_ROOT / 'backend' / 'agrimitra.db').as_posix()}"
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "AgriMitra Backend"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = DEFAULT_DATABASE_URL

    NVIDIA_API_KEY: str = ""
    NVIDIA_MODEL: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    OPENAI_API_BASE: str = "https://integrate.api.nvidia.com/v1"
    DATA_GOV_API_KEY: str = ""
    DATA_GOV_RESOURCE_ID: str = "9ef84268-d588-465a-a308-a864a43d0070"
    DATA_GOV_API_BASE: str = "https://api.data.gov.in/resource"
    DATA_GOV_CACHE_TTL_SECONDS: int = 300
    DATA_GOV_CONNECT_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    DATA_GOV_READ_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=60)
    NVIDIA_REQUEST_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=180)
    APP_ENV: str = "development"
    BACKEND_CORS_ORIGINS: list[str] = Field(default_factory=list)

    class Config:
        env_file = PROJECT_ROOT / ".env"
        extra = "ignore"


settings = Settings()
