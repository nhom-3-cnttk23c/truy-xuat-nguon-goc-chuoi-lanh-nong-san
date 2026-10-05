"""Add immutable events table with append-only triggers and tenant RLS.

Revision ID: 20261005_05
Revises: 20260930_04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

revision: str = "20261005_05"
down_revision: str | None = "20260930_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _application_role() -> str | None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_catalog.pg_roles "
            "WHERE rolname = :role AND :role <> current_user"
        ),
        {"role": settings.DB_USER},
    ).scalar()
    if not exists:
        return None
    return bind.dialect.identifier_preparer.quote(settings.DB_USER)


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "length(btrim(event_type)) > 0", name="ck_events_event_type_nonblank"
        ),
        sa.CheckConstraint("sequence_number > 0", name="ck_events_sequence_positive"),
        sa.CheckConstraint("length(prev_hash) = 64", name="ck_events_prev_hash_length"),
        sa.CheckConstraint(
            "length(event_hash) = 64", name="ck_events_event_hash_length"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_events_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_events_lot_id_lots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lot_id", "sequence_number", name="uq_events_lot_sequence"),
        sa.UniqueConstraint("lot_id", "event_hash", name="uq_events_lot_event_hash"),
    )
    op.create_index("ix_events_organization_id", "events", ["organization_id"])
    op.create_index("ix_events_lot_id", "events", ["lot_id"])
    op.create_index("ix_events_recorded_at", "events", ["recorded_at"])

    # 1. Enable Row Level Security (RLS)
    op.execute("ALTER TABLE events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY events_read_tenant_or_inspector ON events
        FOR SELECT
        USING (
            organization_id = public.app_current_organization_id()
            OR public.app_current_role() = 'inspector'
        )
        """
    )
    op.execute(
        """
        CREATE POLICY events_insert_tenant ON events
        FOR INSERT
        WITH CHECK (
            organization_id = public.app_current_organization_id()
        )
        """
    )

    # 2. Grant least-privilege permissions to application role (N3-21)
    role = _application_role()
    if role:
        op.execute(f"REVOKE UPDATE, DELETE ON events FROM {role}")
        op.execute(f"GRANT SELECT, INSERT ON events TO {role}")

    # 3. Create Immutability Enforcement Triggers (N3-21)
    # Even if someone connects with elevated rights, UPDATE and DELETE are prohibited.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.prevent_event_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            RAISE EXCEPTION 'Events are immutable and append-only. UPDATE and DELETE are prohibited.'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $function$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_prevent_update
            BEFORE UPDATE ON events
            FOR EACH ROW
            EXECUTE FUNCTION public.prevent_event_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_events_prevent_delete
            BEFORE DELETE ON events
            FOR EACH ROW
            EXECUTE FUNCTION public.prevent_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_events_prevent_delete ON events")
    op.execute("DROP TRIGGER IF EXISTS trg_events_prevent_update ON events")
    op.execute("DROP FUNCTION IF EXISTS public.prevent_event_mutation()")

    role = _application_role()
    if role:
        op.execute(f"REVOKE SELECT, INSERT ON events FROM {role}")

    op.execute("DROP POLICY IF EXISTS events_insert_tenant ON events")
    op.execute("DROP POLICY IF EXISTS events_read_tenant_or_inspector ON events")
    op.execute("ALTER TABLE events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE events DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_events_recorded_at", table_name="events")
    op.drop_index("ix_events_lot_id", table_name="events")
    op.drop_index("ix_events_organization_id", table_name="events")
    op.drop_table("events")
