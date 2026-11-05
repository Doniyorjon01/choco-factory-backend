"""
Ilova sozlamalari — hammasi muhit o'zgaruvchilaridan (.env) o'qiladi.

Maxfiy qiymatlar uchun standart qiymat yo'q: SECRET_KEY yoki DATABASE_URL
berilmasa, ilova ishga tushmaydi. Bu sukut bo'yicha xavfsiz kalit bilan
prodga chiqib ketishdan yaxshiroq.
"""

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Chocolate Factory API"
    APP_ENV: Literal["dev", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # postgresql+psycopg://user:pass@host:5432/dbname
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    # Bitta so'rov bundan uzoq ishlasa, Postgres uni to'xtatadi (ms)
    DB_STATEMENT_TIMEOUT_MS: int = 15_000
    # Qulf kutish chegarasi: parallel Produce bir-birini cheksiz kutmasin (ms)
    DB_LOCK_TIMEOUT_MS: int = 5_000

    SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    # Bir smena: 12 soat
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 5

    # Vergul bilan: http://localhost:5173,https://cf.example.uz
    CORS_ORIGINS: str = ""

    # Biznes vaqti: "bugun", "7 kun", yetkazib beruvchi sanasi shu zonada
    TIMEZONE: str = "Asia/Tashkent"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def is_prod(self) -> bool:
        return self.APP_ENV == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
