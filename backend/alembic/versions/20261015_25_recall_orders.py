"""Add recall orders and recall-order lots.

An open recall order blocks lot mutations. A completed recall order keeps
blocking while its lots still carry an incident flag.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

revision: str = "20261015_25"
down_revision: str | Sequence[str] | None = "20261012_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


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
        "recall_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "length(btrim(code)) > 0",
            name="ck_recall_orders_code_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recall_orders_organization_status",
        "recall_orders",
        ["organization_id", "status"],
    )
    op.create_index(
        "uq_recall_orders_code",
        "recall_orders",
        ["code"],
        unique=True,
    )

    op.create_table(
        "recall_order_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recall_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "incident_flag",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["recall_order_id"], ["recall_orders.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["lot_id", "organization_id"],
            ["lots.id", "lots.organization_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recall_order_id", "lot_id", name="uq_recall_order_lots_order_lot"
        ),
    )
    op.create_index(
        "ix_recall_order_lots_lot_incident",
        "recall_order_lots",
        ["lot_id", "incident_flag"],
    )

    op.execute("ALTER TABLE recall_orders ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY recall_orders_admin_only ON recall_orders
        FOR ALL
        USING (public.app_current_role() = 'system_admin')
        WITH CHECK (public.app_current_role() = 'system_admin')
        """
    )
    op.execute("ALTER TABLE recall_order_lots ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY recall_order_lots_admin_only ON recall_order_lots
        FOR ALL
        USING (
            public.app_current_role() = 'system_admin'
            OR EXISTS (
                SELECT 1 FROM public.recall_orders ro
                WHERE ro.id = recall_order_lots.recall_order_id
                  AND ro.organization_id = public.app_current_organization_id()
            )
        )
        WITH CHECK (
            public.app_current_role() = 'system_admin'
            OR EXISTS (
                SELECT 1 FROM public.recall_orders ro
                WHERE ro.id = recall_order_lots.recall_order_id
                  AND ro.organization_id = public.app_current_organization_id()
            )
        )
        """
    )

    role = _application_role()
    if role:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON recall_orders TO {role}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON recall_order_lots TO {role}")


def downgrade() -> None:
    role = _application_role()
    if role:
        op.execute(f"REVOKE ALL ON recall_order_lots FROM {role}")
        op.execute(f"REVOKE ALL ON recall_orders FROM {role}")

    op.execute("DROP POLICY IF EXISTS recall_order_lots_admin_only ON recall_order_lots")
    op.execute("DROP POLICY IF EXISTS recall_orders_admin_only ON recall_orders")
    op.execute("ALTER TABLE recall_order_lots NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recall_order_lots DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recall_orders NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE recall_orders DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_recall_order_lots_lot_incident", table_name="recall_order_lots")
    op.drop_index("uq_recall_orders_code", table_name="recall_orders")
    op.drop_index("ix_recall_orders_organization_status", table_name="recall_orders")
    op.drop_table("recall_order_lots")
    op.drop_table("recall_orders")
