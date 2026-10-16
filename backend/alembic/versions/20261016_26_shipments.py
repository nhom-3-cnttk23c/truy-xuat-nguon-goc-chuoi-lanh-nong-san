"""Add shipments and shipment_lots tables with cold chain RLS policies (N3-58).

Revision ID: 20261016_26
Revises: 20261015_25
Create Date: 2026-10-16 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.config import settings

# revision identifiers, used by Alembic.
revision: str = "20261016_26"
down_revision: str | Sequence[str] | None = "20261015_25"
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
    # 1. Create shipments table
    op.create_table(
        "shipments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shipment_code", sa.String(length=32), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("container_code", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'in_transit'"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('in_transit', 'completed')",
            name="ck_shipments_status_supported",
        ),
        sa.CheckConstraint(
            "length(btrim(shipment_code)) > 0",
            name="ck_shipments_code_nonblank",
        ),
        sa.CheckConstraint(
            "length(btrim(container_code)) > 0",
            name="ck_shipments_container_nonblank",
        ),
        sa.CheckConstraint(
            "(status = 'in_transit' AND completed_at IS NULL) OR (status = 'completed' AND completed_at IS NOT NULL)",
            name="ck_shipments_completion_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_shipments_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_shipments_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shipment_code", name="uq_shipments_shipment_code"),
    )
    op.create_index(
        "ix_shipments_organization_id",
        "shipments",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_shipments_status",
        "shipments",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_shipments_container_code",
        "shipments",
        ["container_code"],
        unique=False,
    )

    # 2. Create shipment_lots table
    op.create_table(
        "shipment_lots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shipment_id", sa.UUID(), nullable=False),
        sa.Column("lot_id", sa.UUID(), nullable=False),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("unloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["shipment_id"],
            ["shipments.id"],
            name="fk_shipment_lots_shipment_id_shipments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_shipment_lots_lot_id_lots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shipment_id", "lot_id", name="uq_shipment_lots_shipment_lot"
        ),
    )
    op.create_index(
        "ix_shipment_lots_shipment_id",
        "shipment_lots",
        ["shipment_id"],
        unique=False,
    )
    op.create_index(
        "ix_shipment_lots_lot_id",
        "shipment_lots",
        ["lot_id"],
        unique=False,
    )
    # NFR (N3-58): một lô chỉ nằm trong một chuyến đang chạy tại một thời điểm
    op.create_index(
        "uq_shipment_lots_active_lot",
        "shipment_lots",
        ["lot_id"],
        unique=True,
        postgresql_where=sa.text("unloaded_at IS NULL"),
    )

    # 3. Enable RLS and create policies on shipments
    op.execute("ALTER TABLE shipments ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY shipments_read ON shipments
        FOR SELECT
        USING (
            organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
        )
        """
    )
    op.execute(
        """
        CREATE POLICY shipments_insert ON shipments
        FOR INSERT
        WITH CHECK (
            organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('system_admin')
        )
        """
    )
    op.execute(
        """
        CREATE POLICY shipments_update ON shipments
        FOR UPDATE
        USING (
            organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('system_admin')
        )
        WITH CHECK (
            organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('system_admin')
        )
        """
    )

    # 4. Enable RLS and create policies on shipment_lots
    op.execute("ALTER TABLE shipment_lots ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY shipment_lots_read ON shipment_lots
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM public.shipments AS s
                WHERE s.id = shipment_lots.shipment_id
                  AND (
                      s.organization_id = public.app_current_organization_id()
                      OR public.app_current_role() IN ('inspector', 'system_admin')
                  )
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY shipment_lots_insert ON shipment_lots
        FOR INSERT
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM public.shipments AS s
                WHERE s.id = shipment_lots.shipment_id
                  AND (
                      s.organization_id = public.app_current_organization_id()
                      OR public.app_current_role() IN ('system_admin')
                  )
            )
        )
        """
    )
    op.execute(
        """
        CREATE POLICY shipment_lots_update ON shipment_lots
        FOR UPDATE
        USING (
            EXISTS (
                SELECT 1 FROM public.shipments AS s
                WHERE s.id = shipment_lots.shipment_id
                  AND (
                      s.organization_id = public.app_current_organization_id()
                      OR public.app_current_role() IN ('system_admin')
                  )
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM public.shipments AS s
                WHERE s.id = shipment_lots.shipment_id
                  AND (
                      s.organization_id = public.app_current_organization_id()
                      OR public.app_current_role() IN ('system_admin')
                  )
            )
        )
        """
    )

    # 5. Update events_insert_tenant policy to permit shipment_loaded and shipment_unloaded
    op.execute("DROP POLICY IF EXISTS events_insert_tenant ON events")
    op.execute(
        """
        CREATE POLICY events_insert_tenant ON events
        FOR INSERT
        WITH CHECK (
            organization_id = public.app_current_organization_id()
            AND (
                EXISTS (
                    SELECT 1 FROM public.lots AS l
                    WHERE l.id = events.lot_id
                      AND l.current_holder_organization_id = public.app_current_organization_id()
                )
                OR (
                    event_type IN ('handover_accepted', 'handover_rejected')
                    AND EXISTS (
                        SELECT 1 FROM public.handovers AS h
                        WHERE h.lot_id = events.lot_id
                          AND h.to_organization_id = public.app_current_organization_id()
                          AND h.status = 'pending'
                    )
                )
                OR (
                    event_type IN ('recall_opened', 'recall_completed')
                    AND public.app_current_role() IN ('inspector', 'system_admin')
                )
                OR (
                    event_type IN ('shipment_loaded', 'shipment_unloaded')
                )
            )
        )
        """
    )

    # 6. Grant table permissions to application role
    role = _application_role()
    if role:
        op.execute(f"GRANT SELECT, INSERT ON shipments TO {role}")
        op.execute(f"GRANT UPDATE (status, completed_at, notes) ON shipments TO {role}")
        op.execute(f"GRANT SELECT, INSERT ON shipment_lots TO {role}")
        op.execute(f"GRANT UPDATE (unloaded_at) ON shipment_lots TO {role}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS events_insert_tenant ON events")
    op.execute(
        """
        CREATE POLICY events_insert_tenant ON events
        FOR INSERT
        WITH CHECK (
            organization_id = public.app_current_organization_id()
            AND (
                EXISTS (
                    SELECT 1 FROM public.lots AS l
                    WHERE l.id = events.lot_id
                      AND l.current_holder_organization_id = public.app_current_organization_id()
                )
                OR (
                    event_type IN ('handover_accepted', 'handover_rejected')
                    AND EXISTS (
                        SELECT 1 FROM public.handovers AS h
                        WHERE h.lot_id = events.lot_id
                          AND h.to_organization_id = public.app_current_organization_id()
                          AND h.status = 'pending'
                    )
                )
                OR (
                    event_type IN ('recall_opened', 'recall_completed')
                    AND public.app_current_role() IN ('inspector', 'system_admin')
                )
            )
        )
        """
    )
    op.drop_table("shipment_lots")
    op.drop_table("shipments")
