"""Add recall_orders table and RLS policies (N3-49).

Revision ID: 20261015_25
Revises: 20261012_24
Create Date: 2026-10-15 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "20261015_25"
down_revision: str | Sequence[str] | None = "20261012_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _application_role() -> str | None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :role AND :role <> current_user"
        ),
        {"role": settings.DB_USER},
    ).scalar()
    return bind.dialect.identifier_preparer.quote(settings.DB_USER) if exists else None


def upgrade() -> None:
    op.create_table(
        "recall_orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("recall_code", sa.String(length=32), nullable=False),
        sa.Column("root_lot_id", sa.UUID(), nullable=False),
        sa.Column("opened_by_user_id", sa.UUID(), nullable=False),
        sa.Column("opened_by_organization_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'completed')",
            name="ck_recall_orders_status_supported",
        ),
        sa.CheckConstraint(
            "length(btrim(recall_code)) > 0",
            name="ck_recall_orders_code_nonblank",
        ),
        sa.CheckConstraint(
            "length(btrim(reason)) >= 20",
            name="ck_recall_orders_reason_min_length",
        ),
        sa.ForeignKeyConstraint(
            ["root_lot_id"],
            ["lots.id"],
            name="fk_recall_orders_root_lot_id_lots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_user_id"],
            ["users.id"],
            name="fk_recall_orders_opened_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_organization_id"],
            ["organizations.id"],
            name="fk_recall_orders_opened_by_org_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recall_code", name="uq_recall_orders_recall_code"),
    )
    op.create_index(
        "ix_recall_orders_root_lot_id",
        "recall_orders",
        ["root_lot_id"],
        unique=False,
    )
    op.create_index(
        "ix_recall_orders_status",
        "recall_orders",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_recall_orders_opened_by_org_id",
        "recall_orders",
        ["opened_by_organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_recall_orders_open_root_lot",
        "recall_orders",
        ["root_lot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.execute("ALTER TABLE recall_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY recall_orders_read ON recall_orders
        FOR SELECT
        USING (
            opened_by_organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
            OR EXISTS (
                SELECT 1 FROM public.lots AS l
                WHERE l.id = recall_orders.root_lot_id
                  AND l.current_holder_organization_id = public.app_current_organization_id()
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY recall_orders_insert ON recall_orders
        FOR INSERT
        WITH CHECK (
            opened_by_organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
        )
        """
    )
    op.execute(
        """
        CREATE POLICY recall_orders_update ON recall_orders
        FOR UPDATE
        USING (
            opened_by_organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
        )
        WITH CHECK (
            opened_by_organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
        )
        """
    )

    role = _application_role()
    if role:
        op.execute(f"GRANT SELECT, INSERT ON recall_orders TO {role}")
        op.execute(f"GRANT UPDATE (status, completed_at) ON recall_orders TO {role}")


def downgrade() -> None:
    op.drop_table("recall_orders")
