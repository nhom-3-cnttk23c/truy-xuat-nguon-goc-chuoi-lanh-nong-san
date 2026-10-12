from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


def _normalize_postgres_url(value: str) -> URL:
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+psycopg://", 1)
    elif value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return make_url(value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "ttcs_db"
    DB_USER: str = "ttcs_app"
    DB_PASSWORD: str = ""
    DB_ADMIN_USER: str = "admin"
    DB_ADMIN_PASSWORD: str = ""
    DATABASE_URL_ENV: str | None = None
    MIGRATION_DATABASE_URL_ENV: str | None = None

    APP_ENV: str = "production"
    DEBUG: bool = False
    DEMO_PASSWORD: str | None = None
    LOGIN_LOCK_MINUTES: int = Field(default=15, ge=1, le=1440)
    SESSION_TTL_MINUTES: int = Field(default=480, ge=1, le=10080)
    HANDOVER_OVERDUE_HOURS: int = Field(default=48, ge=1, le=8760)
    SESSION_COOKIE_NAME: str = "__Host-session"
    SESSION_COOKIE_SAMESITE: str = "none"
    SESSION_COOKIE_SECURE: bool = True
    ALLOWED_ORIGINS: list[str] | str = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://ttcs-frontend-staging.onrender.com",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        else:
            origins = value
        if "*" in origins:
            raise ValueError("ALLOWED_ORIGINS cannot include a wildcard origin")
        return origins

    @model_validator(mode="after")
    def require_separate_database_roles(self) -> "Settings":
        if self.DB_USER == self.DB_ADMIN_USER:
            raise ValueError("DB_USER and DB_ADMIN_USER must be different")
        return self

    def validate_runtime(self, *, migrate: bool = False) -> None:
        """Fail before serving traffic, without including credential values."""
        if not self.DATABASE_URL.password:
            raise ValueError("Thiếu DB_PASSWORD hoặc DATABASE_URL_ENV có mật khẩu")
        if self.DATABASE_URL.username == self.DB_ADMIN_USER:
            raise ValueError(
                "DATABASE_URL_ENV phải dùng DB_USER, không dùng DB_ADMIN_USER"
            )
        if migrate and not self.MIGRATION_DATABASE_URL.password:
            raise ValueError("Thiếu DB_ADMIN_PASSWORD hoặc MIGRATION_DATABASE_URL_ENV")

    @property
    def DATABASE_URL(self) -> URL:
        if self.DATABASE_URL_ENV:
            url = _normalize_postgres_url(self.DATABASE_URL_ENV)
            if self.DB_PASSWORD and url.username != self.DB_USER:
                return url.set(username=self.DB_USER, password=self.DB_PASSWORD)
            return url

        return URL.create(
            "postgresql+psycopg",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )

    @property
    def MIGRATION_DATABASE_URL(self) -> URL:
        if self.MIGRATION_DATABASE_URL_ENV:
            url = _normalize_postgres_url(self.MIGRATION_DATABASE_URL_ENV)
            if self.DB_ADMIN_PASSWORD and url.username != self.DB_ADMIN_USER:
                return url.set(
                    username=self.DB_ADMIN_USER,
                    password=self.DB_ADMIN_PASSWORD,
                )
            return url

        if self.DATABASE_URL_ENV:
            if self.DB_ADMIN_PASSWORD:
                url = _normalize_postgres_url(self.DATABASE_URL_ENV)
                return url.set(
                    username=self.DB_ADMIN_USER,
                    password=self.DB_ADMIN_PASSWORD,
                )
            return self.DATABASE_URL

        return URL.create(
            "postgresql+psycopg",
            username=self.DB_ADMIN_USER,
            password=self.DB_ADMIN_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=self.DB_NAME,
        )


settings = Settings()
