"""Add batch lineage, transactions, batch_relations, and batch_events for lot split/merge.

Revision ID: 20261009_16
Revises: 20261007_14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.config import settings

revision: str = "20261009_16"
down_revision: str | None = "20261007_14"
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
    # ============================================================================
    # 1. Extend lots table with lineage columns
    # ============================================================================
    op.add_column(
        "lots",
        sa.Column("parent_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "lots",
        sa.Column("lineage_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "lots",
        sa.Column("root_harvest_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Update existing lots: root_harvest_id points to self (root of chain)
    op.execute("UPDATE lots SET root_harvest_id = id, lineage_depth = 0")

    # Add foreign key for parent_batch_id (self-referential)
    op.create_foreign_key(
        "fk_lots_parent_batch_id_lots",
        "lots",
        "lots",
        ["parent_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Add check constraint to prevent self-loop
    op.create_check_constraint(
        "ck_lots_parent_not_self",
        "lots",
        "parent_batch_id IS NULL OR parent_batch_id <> id",
    )

    # Add indexes for lineage queries
    op.create_index(
        "ix_lots_parent_batch_id",
        "lots",
        ["parent_batch_id"],
    )
    op.create_index(
        "ix_lots_root_harvest_id_depth",
        "lots",
        ["root_harvest_id", "lineage_depth"],
    )

    # ============================================================================
    # 2. Create transactions table (atomic split/merge boundaries)
    # ============================================================================
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("initiator_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "initiator_organization_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column(
            "op_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="'pending'",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "op_type IN ('split', 'merge')", name="ck_transactions_op_type"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'committed', 'rolled_back')",
            name="ck_transactions_status",
        ),
        sa.ForeignKeyConstraint(
            ["initiator_user_id"],
            ["users.id"],
            name="fk_transactions_initiator_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiator_organization_id"],
            ["organizations.id"],
            name="fk_transactions_initiator_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index("ix_transactions_created_at", "transactions", ["created_at"])

    # ============================================================================
    # 3. Create batch_relations table (DAG edges for split/merge)
    # ============================================================================
    op.create_table(
        "batch_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "weight_transferred",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
        ),
        sa.Column(
            "op_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weight_transferred > 0", name="ck_batch_relations_weight_positive"
        ),
        sa.CheckConstraint(
            "op_type IN ('split', 'merge')",
            name="ck_batch_relations_op_type",
        ),
        sa.CheckConstraint(
            "parent_batch_id <> child_batch_id",
            name="ck_batch_relations_not_self_loop",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_batch_relations_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_batch_id"],
            ["lots.id"],
            name="fk_batch_relations_parent_batch_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["child_batch_id"],
            ["lots.id"],
            name="fk_batch_relations_child_batch_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_batch_relations_parent",
        "batch_relations",
        ["parent_batch_id"],
    )
    op.create_index(
        "ix_batch_relations_child",
        "batch_relations",
        ["child_batch_id"],
    )
    op.create_index(
        "ix_batch_relations_transaction",
        "batch_relations",
        ["transaction_id"],
    )

    # ============================================================================
    # 4. Create batch_events table (immutable append-only event log per lot)
    # ============================================================================
    op.create_table(
        "batch_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(event_type) > 0", name="ck_batch_events_event_type"),
        sa.CheckConstraint(
            "length(prev_hash) = 64", name="ck_batch_events_prev_hash_len"
        ),
        sa.CheckConstraint("length(hash) = 64", name="ck_batch_events_hash_len"),
        sa.UniqueConstraint(
            "batch_id", "event_id", name="uq_batch_events_batch_event_id"
        ),
        sa.UniqueConstraint("batch_id", "hash", name="uq_batch_events_batch_hash"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["lots.id"],
            name="fk_batch_events_batch_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_batch_events_actor_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["transactions.id"],
            name="fk_batch_events_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_batch_events_batch_id", "batch_events", ["batch_id"])
    op.create_index("ix_batch_events_actor_user_id", "batch_events", ["actor_user_id"])
    op.create_index("ix_batch_events_recorded_at", "batch_events", ["recorded_at"])

    # ============================================================================
    # 5. Create immutability triggers on batch_events
    # ============================================================================
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_batch_events_prevent_update()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'batch_events are immutable and cannot be updated';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_batch_events_no_update
        BEFORE UPDATE ON batch_events
        FOR EACH ROW
        EXECUTE FUNCTION trg_batch_events_prevent_update();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_batch_events_prevent_delete()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'batch_events are immutable and cannot be deleted';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_batch_events_no_delete
        BEFORE DELETE ON batch_events
        FOR EACH ROW
        EXECUTE FUNCTION trg_batch_events_prevent_delete();
        """
    )

    # ============================================================================
    # 6. Enable RLS on new tables and create policies
    # ============================================================================
    op.execute("ALTER TABLE transactions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE batch_relations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE batch_events ENABLE ROW LEVEL SECURITY")

    # transactions: visible to initiator org + system_admin + inspector
    op.execute(
        """
        CREATE POLICY transactions_read_tenant_or_auditor ON transactions
        FOR SELECT
        USING (
            initiator_organization_id = public.app_current_organization_id()
            OR public.app_current_role() IN ('inspector', 'system_admin')
        )
        """
    )

    # batch_relations: visible through lineage (parent org, child org, or auditors)
    op.execute(
        """
        CREATE POLICY batch_relations_read_lineage ON batch_relations
        FOR SELECT
        USING (
            public.app_current_role() IN ('inspector', 'system_admin')
            OR EXISTS (
                SELECT 1 FROM lots l
                WHERE l.id = batch_relations.parent_batch_id
                AND l.organization_id = public.app_current_organization_id()
            )
            OR EXISTS (
                SELECT 1 FROM lots l
                WHERE l.id = batch_relations.child_batch_id
                AND l.organization_id = public.app_current_organization_id()
            )
        )
        """
    )

    # batch_events: visible through lot lineage + event_type visibility
    op.execute(
        """
        CREATE POLICY batch_events_read_lineage ON batch_events
        FOR SELECT
        USING (
            public.app_current_role() IN ('inspector', 'system_admin')
            OR EXISTS (
                SELECT 1 FROM lots l
                WHERE l.id = batch_events.batch_id
                AND l.organization_id = public.app_current_organization_id()
            )
        )
        """
    )

    # Grant permissions to application role
    role = _application_role()
    if role:
        op.execute(f"GRANT SELECT, INSERT ON transactions TO {role}")
        op.execute(f"GRANT UPDATE (status, committed_at) ON transactions TO {role}")
        op.execute(f"GRANT SELECT, INSERT ON batch_relations TO {role}")
        op.execute(f"GRANT SELECT, INSERT ON batch_events TO {role}")


def downgrade() -> None:
    role = _application_role()
    if role:
        op.execute(f"REVOKE SELECT, INSERT ON batch_events FROM {role}")
        op.execute(f"REVOKE SELECT, INSERT ON batch_relations FROM {role}")
        op.execute(f"REVOKE UPDATE (status, committed_at) ON transactions FROM {role}")
        op.execute(f"REVOKE SELECT, INSERT ON transactions FROM {role}")

    op.execute("ALTER TABLE batch_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE batch_events DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS batch_events_read_lineage ON batch_events")

    op.execute("ALTER TABLE batch_relations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE batch_relations DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS batch_relations_read_lineage ON batch_relations")

    op.execute("ALTER TABLE transactions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transactions DISABLE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS transactions_read_tenant_or_auditor ON transactions"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_batch_events_no_delete ON batch_events")
    op.execute("DROP FUNCTION IF EXISTS trg_batch_events_prevent_delete()")
    op.execute("DROP TRIGGER IF EXISTS trg_batch_events_no_update ON batch_events")
    op.execute("DROP FUNCTION IF EXISTS trg_batch_events_prevent_update()")

    op.drop_table("batch_events")
    op.drop_table("batch_relations")
    op.drop_table("transactions")

    op.drop_index("ix_lots_root_harvest_id_depth", table_name="lots")
    op.drop_index("ix_lots_parent_batch_id", table_name="lots")
    op.drop_constraint("ck_lots_parent_not_self", "lots", type_="check")
    op.drop_constraint(
        "fk_lots_parent_batch_id_lots",
        "lots",
        type_="foreignkey",
    )

    op.drop_column("lots", "root_harvest_id")
    op.drop_column("lots", "lineage_depth")
    op.drop_column("lots", "parent_batch_id")
