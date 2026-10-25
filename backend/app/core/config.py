from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int
    api_v1_str: str = "/api/v1"
    frontend_host: str = "http://localhost:5173"
    project_name: str = "WOT tournaments"

    wg_authenticate_url: str = "https://api.worldoftanks.eu/wot/auth/login/"
    wg_app_id: str
    wg_redirect_uri: str = "http://localhost:8000/api/v1/auth/wargaming/callback"


    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore