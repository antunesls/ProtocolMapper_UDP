from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Web server
    host: str = "0.0.0.0"
    port: int = 8000

    # Admin credentials
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # UDP defaults (initial values; runtime values live in DB)
    udp_listen_ip: str = "0.0.0.0"
    udp_listen_port: int = 5005

    # Database
    database_url: str = "data/mapper.db"

    # Logging
    log_max_entries: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
