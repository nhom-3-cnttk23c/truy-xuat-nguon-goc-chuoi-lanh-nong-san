"""Bootstrap PostgreSQL with the migration role, then run as the app role."""

import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.bootstrap_db_role import bootstrap_database_role
from app.core.config import settings
from app.seed_demo import seed_demo_data

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    alembic_cfg = Config(str(ini_path))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    logger.info("Starting database migration (alembic upgrade head)...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migration completed successfully.")


def _runtime_environment(
    app_database_url: str, source: Mapping[str, str]
) -> dict[str, str]:
    runtime_environment = dict(source)
    runtime_environment["DATABASE_URL_ENV"] = app_database_url
    runtime_environment.pop("MIGRATION_DATABASE_URL_ENV", None)
    runtime_environment.pop("DB_ADMIN_PASSWORD", None)
    return runtime_environment


def main() -> None:
    settings.validate_runtime(migrate=True)
    try:
        bootstrap_database_role()
    except Exception:
        logger.critical("Database role bootstrap failed; startup stopped.")
        raise SystemExit(1) from None

    try:
        run_migrations()
    except Exception:
        logger.critical("Database migration failed; startup stopped.")
        raise SystemExit(1) from None

    seed_demo_data()

    runtime_environment = _runtime_environment(
        settings.DATABASE_URL.render_as_string(hide_password=False),
        os.environ,
    )

    port = runtime_environment.get("PORT", "8000")
    os.execvpe(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
        runtime_environment,
    )


if __name__ == "__main__":
    main()
