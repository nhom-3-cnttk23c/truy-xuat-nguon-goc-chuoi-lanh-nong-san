from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

from app.bootstrap_db_role import bootstrap_database_role
from app.core.config import settings
from app.core.security import hash_password, hash_session_token
from app.models.event import Event
from app.models.farm import Farm
from app.models.handover import Handover
from app.models.identity import AuthSession, Organization, Role, User
from app.models.integrity_check import IntegrityCheck
from app.models.lot import Lot
from app.models.lot_relation import LotRelation
from app.models.recall_order import RecallOrder


def pytest_sessionstart(session):
    """Stop before fixtures or tests can mutate the local presentation database."""
    for url in (settings.DATABASE_URL, settings.MIGRATION_DATABASE_URL):
        if (
            url.host in {"127.0.0.1", "localhost"}
            and url.port == 55434
            and url.database == "ttcs_test"
        ):
            raise pytest.UsageError(
                "DB trình diễn không dùng để chạy test. Dùng scripts/test-local.ps1 "
                "với DB ttcs_s34_tests."
            )


@dataclass(frozen=True)
class IdentityFixture:
    organization_id: UUID
    user_id: UUID
    email: str
    password: str
    session_token_hash: str


@pytest.fixture(scope="session")
def admin_engine():
    engine = create_engine(
        settings.MIGRATION_DATABASE_URL,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
    )
    bootstrap_database_role()
    yield engine
    engine.dispose()


@pytest.fixture
def admin_session(admin_engine) -> Iterator[Session]:
    with Session(admin_engine) as session:
        yield session


@pytest.fixture
def identity_factory(
    admin_session: Session,
) -> Iterator[Callable[..., IdentityFixture]]:
    created_organizations: list[UUID] = []
    created_users: list[UUID] = []

    def create_identity(
        *, role: str = "grower", organization_type: str = "farm"
    ) -> IdentityFixture:
        suffix = uuid4().hex
        if admin_session.get(Role, role) is None:
            raise AssertionError(f"Role was not seeded by migration: {role}")

        organization = Organization(
            name=f"integration-{suffix}",
            organization_type=organization_type,
            is_active=True,
        )
        admin_session.add(organization)
        admin_session.flush()

        password = "Correct horse battery staple 2026!"
        user = User(
            organization_id=organization.id,
            role_code=role,
            email=f"{suffix}@example.com",
            full_name="Integration test user",
            password_hash=hash_password(password),
            failed_login_attempts=0,
            locked_until=None,
            is_active=True,
        )
        admin_session.add(user)
        admin_session.flush()

        session_token_hash = hash_session_token(f"rls-test-{suffix}")
        now = datetime.now(UTC)
        admin_session.add(
            AuthSession(
                user_id=user.id,
                token_hash=session_token_hash,
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
        )
        admin_session.commit()

        created_organizations.append(organization.id)
        created_users.append(user.id)
        return IdentityFixture(
            organization_id=organization.id,
            user_id=user.id,
            email=user.email,
            password=password,
            session_token_hash=session_token_hash,
        )

    yield create_identity

    if created_organizations:
        lot_ids = list(
            admin_session.scalars(
                select(Lot.id).where(Lot.organization_id.in_(created_organizations))
            ).all()
        )
        if lot_ids:
            with admin_session.begin_nested():
                admin_session.execute(
                    text("ALTER TABLE lot_relations DISABLE TRIGGER USER")
                )
                admin_session.execute(
                    delete(LotRelation).where(
                        (LotRelation.parent_lot_id.in_(lot_ids))
                        | (LotRelation.child_lot_id.in_(lot_ids))
                    )
                )
                admin_session.execute(
                    text("ALTER TABLE lot_relations ENABLE TRIGGER USER")
                )
                admin_session.execute(text("ALTER TABLE events DISABLE TRIGGER USER"))
                admin_session.execute(
                    text("ALTER TABLE integrity_checks DISABLE TRIGGER USER")
                )
                admin_session.execute(
                    delete(Handover).where(Handover.lot_id.in_(lot_ids))
                )
                admin_session.execute(
                    delete(IntegrityCheck).where(IntegrityCheck.lot_id.in_(lot_ids))
                )
                admin_session.execute(delete(Event).where(Event.lot_id.in_(lot_ids)))
                admin_session.execute(
                    delete(RecallOrder).where(RecallOrder.root_lot_id.in_(lot_ids))
                )
                admin_session.execute(delete(Lot).where(Lot.id.in_(lot_ids)))
                admin_session.execute(
                    text("ALTER TABLE integrity_checks ENABLE TRIGGER USER")
                )
                admin_session.execute(text("ALTER TABLE events ENABLE TRIGGER USER"))
        admin_session.execute(
            delete(Farm).where(Farm.organization_id.in_(created_organizations))
        )
    if created_users:
        admin_session.execute(
            delete(AuthSession).where(AuthSession.user_id.in_(created_users))
        )
        admin_session.execute(delete(User).where(User.id.in_(created_users)))
    if created_organizations:
        admin_session.execute(
            delete(Organization).where(Organization.id.in_(created_organizations))
        )
    admin_session.commit()
