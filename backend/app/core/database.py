from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.orm.session import SessionTransaction

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 5}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_RLS_CONTEXT: dict[str, str] = {
    "session_token_hash": "app.session_token_hash",
    "login_email": "app.login_email",
}


def set_db_context(db: Session, **values: object) -> None:
    """Set trusted, transaction-local context used by PostgreSQL RLS policies."""
    for key, value in values.items():
        setting_name = _RLS_CONTEXT.get(key)
        if setting_name is None:
            raise ValueError(f"Unsupported database context value: {key}")

        setting_value = "" if value is None else str(value)
        db.info[key] = setting_value
        db.execute(
            text("SELECT set_config(:setting_name, :setting_value, true)"),
            {"setting_name": setting_name, "setting_value": setting_value},
        )


@event.listens_for(SessionLocal, "after_begin")
def set_database_tenant_context(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    for key, setting_name in _RLS_CONTEXT.items():
        value = session.info.get(key)
        if value is not None:
            connection.execute(
                text("SELECT set_config(:setting_name, :setting_value, true)"),
                {"setting_name": setting_name, "setting_value": str(value)},
            )


class Base(DeclarativeBase):
    """Base class cho tất cả SQLAlchemy models trong dự án."""


def get_db():
    """Dependency injection: cung cấp DB session cho mỗi request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
