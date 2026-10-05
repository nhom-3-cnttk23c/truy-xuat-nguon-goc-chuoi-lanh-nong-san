"""Create a least-privilege PostgreSQL role for application requests."""

import logging

from psycopg import sql
from sqlalchemy import create_engine

from app.core.config import settings

logger = logging.getLogger(__name__)


def _grant_existing_table_permissions(cursor, app_role: str) -> None:
    role_ident = sql.Identifier(app_role)
    cursor.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables = {row[0] for row in cursor.fetchall()}

    if "organizations" in tables:
        cursor.execute(
            sql.SQL("GRANT SELECT ON organizations TO {}").format(role_ident)
        )
    if "roles" in tables:
        cursor.execute(sql.SQL("GRANT SELECT ON roles TO {}").format(role_ident))
    if "users" in tables:
        cursor.execute(sql.SQL("GRANT SELECT ON users TO {}").format(role_ident))
        cursor.execute(
            sql.SQL(
                "GRANT UPDATE (failed_login_attempts, locked_until) ON users TO {}"
            ).format(role_ident)
        )
    if "sessions" in tables:
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON sessions TO {}").format(role_ident)
        )
        cursor.execute(
            sql.SQL("GRANT UPDATE (revoked_at) ON sessions TO {}").format(role_ident)
        )
    if "farms" in tables:
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE ON farms TO {}").format(role_ident)
        )
    if "lots" in tables:
        cursor.execute(sql.SQL("GRANT SELECT ON lots TO {}").format(role_ident))
        cursor.execute(
            sql.SQL("REVOKE INSERT, UPDATE, DELETE ON lots FROM {}").format(role_ident)
        )
    if "events" in tables:
        cursor.execute(
            sql.SQL("GRANT SELECT, INSERT ON events TO {}").format(role_ident)
        )
        cursor.execute(
            sql.SQL("REVOKE UPDATE, DELETE ON events FROM {}").format(role_ident)
        )

    cursor.execute(
        "SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public'"
    )
    routines = {row[0] for row in cursor.fetchall()}
    for func in (
        "app_current_user_id",
        "app_current_organization_id",
        "app_current_role",
    ):
        if func in routines:
            cursor.execute(
                sql.SQL("GRANT EXECUTE ON FUNCTION public.{}() TO {}").format(
                    sql.Identifier(func), role_ident
                )
            )


def bootstrap_database_role() -> None:
    app_url = settings.DATABASE_URL
    admin_url = settings.MIGRATION_DATABASE_URL

    if app_url.username == admin_url.username:
        return
    if not app_url.password or not admin_url.password:
        raise RuntimeError("Database passwords must be configured through environment")

    engine = create_engine(admin_url)
    try:
        with engine.begin() as connection:
            raw_connection = connection.connection.driver_connection
            with raw_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT rolsuper, rolcreaterole FROM pg_catalog.pg_roles "
                    "WHERE rolname = current_user"
                )
                row = cursor.fetchone()
                if not row or not (row[0] or row[1]):
                    logger.warning(
                        "Current database user lacks CREATEROLE or SUPERUSER privilege; skipping role bootstrap"
                    )
                    return

                is_super = bool(row[0])

                cursor.execute(
                    "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s",
                    (settings.DB_USER,),
                )
                role_exists = cursor.fetchone() is not None

                if is_super:
                    if not role_exists:
                        cursor.execute(
                            sql.SQL(
                                "CREATE ROLE {} WITH LOGIN NOINHERIT PASSWORD {} "
                                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                            ).format(
                                sql.Identifier(settings.DB_USER),
                                sql.Literal(app_url.password),
                            )
                        )
                    else:
                        cursor.execute(
                            sql.SQL(
                                "ALTER ROLE {} WITH LOGIN NOINHERIT PASSWORD {} "
                                "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                            ).format(
                                sql.Identifier(settings.DB_USER),
                                sql.Literal(app_url.password),
                            )
                        )
                else:
                    # In PostgreSQL 16+ on managed cloud providers (e.g. Render),
                    # non-superusers cannot specify NOSUPERUSER, NOREPLICATION, or NOBYPASSRLS.
                    # Omitting them defaults to false safely.
                    if not role_exists:
                        cursor.execute(
                            sql.SQL(
                                "CREATE ROLE {} WITH LOGIN NOINHERIT PASSWORD {}"
                            ).format(
                                sql.Identifier(settings.DB_USER),
                                sql.Literal(app_url.password),
                            )
                        )
                    else:
                        cursor.execute(
                            sql.SQL(
                                "ALTER ROLE {} WITH LOGIN NOINHERIT PASSWORD {}"
                            ).format(
                                sql.Identifier(settings.DB_USER),
                                sql.Literal(app_url.password),
                            )
                        )

                cursor.execute("SELECT current_database()")
                db_row = cursor.fetchone()
                if db_row and db_row[0] and isinstance(db_row[0], str):
                    cursor.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(db_row[0]),
                            sql.Identifier(settings.DB_USER),
                        )
                    )

                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                        sql.Identifier(settings.DB_USER)
                    )
                )

                _grant_existing_table_permissions(cursor, settings.DB_USER)
    finally:
        engine.dispose()


if __name__ == "__main__":
    bootstrap_database_role()
