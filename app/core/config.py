from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://hotel:hotel_dev_password@localhost:5433/hotel"
    jwt_secret: str = Field(min_length=32)
    jwt_minutes: int = Field(default=60, ge=1)
    hold_minutes: int = Field(default=30, ge=1)
    seed_password: str = Field(default="HotelDemo123!", min_length=10)
    worker_interval_seconds: int = Field(default=5, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
