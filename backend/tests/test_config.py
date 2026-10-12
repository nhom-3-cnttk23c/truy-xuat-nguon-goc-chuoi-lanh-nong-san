import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.startup import _runtime_environment


def test_runtime_and_migration_urls_use_separate_database_roles():
    admin_url = "postgresql://admin:admin-secret@db.example:5432/ttcs"
    settings = Settings(
        _env_file=None,
        DATABASE_URL_ENV=admin_url,
        MIGRATION_DATABASE_URL_ENV=admin_url,
        DB_USER="ttcs_app",
        DB_PASSWORD="app-secret",
        DB_ADMIN_USER="admin",
        DB_ADMIN_PASSWORD="admin-secret",
    )

    assert settings.DATABASE_URL.username == "ttcs_app"
    assert settings.DATABASE_URL.password == "app-secret"
    assert settings.MIGRATION_DATABASE_URL.username == "admin"
    assert settings.MIGRATION_DATABASE_URL.password == "admin-secret"

    runtime_env = _runtime_environment(
        settings.DATABASE_URL.render_as_string(hide_password=False),
        {
            "DATABASE_URL_ENV": admin_url,
            "MIGRATION_DATABASE_URL_ENV": admin_url,
            "DB_ADMIN_PASSWORD": "admin-secret",
            "DB_PASSWORD": "app-secret",
        },
    )
    runtime_settings = Settings(
        _env_file=None,
        DATABASE_URL_ENV=runtime_env["DATABASE_URL_ENV"],
        MIGRATION_DATABASE_URL_ENV=None,
        DB_USER="ttcs_app",
        DB_PASSWORD=runtime_env["DB_PASSWORD"],
        DB_ADMIN_USER="admin",
        DB_ADMIN_PASSWORD="",
        APP_ENV="production",
        DEBUG=False,
    )

    assert runtime_settings.DATABASE_URL.username == "ttcs_app"
    assert runtime_settings.MIGRATION_DATABASE_URL.username == "ttcs_app"
    assert "MIGRATION_DATABASE_URL_ENV" not in runtime_env
    assert "DB_ADMIN_PASSWORD" not in runtime_env


def test_production_is_the_default_environment_and_debug_is_off(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    settings = Settings(_env_file=None)

    assert settings.APP_ENV == "production"
    assert settings.DEBUG is False


def test_runtime_rejects_missing_credentials_without_values():
    settings = Settings(_env_file=None, DB_PASSWORD="", DATABASE_URL_ENV=None)
    with pytest.raises(ValueError, match="DB_PASSWORD"):
        settings.validate_runtime()


def test_runtime_rejects_admin_url():
    settings = Settings(
        _env_file=None,
        DB_PASSWORD="",
        DB_ADMIN_USER="admin",
        DATABASE_URL_ENV="postgresql://admin:secret@localhost/db",
    )
    with pytest.raises(ValueError, match="DB_USER"):
        settings.validate_runtime()


def test_cors_rejects_wildcard_origin_with_cookie_authentication():
    with pytest.raises(ValidationError, match="wildcard origin"):
        Settings(_env_file=None, ALLOWED_ORIGINS="https://app.example,*")


def test_runtime_and_admin_database_roles_must_be_distinct():
    with pytest.raises(ValidationError, match="must be different"):
        Settings(_env_file=None, DB_USER="ttcs", DB_ADMIN_USER="ttcs")


def test_run_migrations_invokes_alembic_upgrade(monkeypatch):
    from unittest.mock import MagicMock

    import alembic.command

    from app.startup import run_migrations

    mock_upgrade = MagicMock()
    monkeypatch.setattr(alembic.command, "upgrade", mock_upgrade)

    run_migrations()

    mock_upgrade.assert_called_once()
    assert mock_upgrade.call_args[0][1] == "head"
