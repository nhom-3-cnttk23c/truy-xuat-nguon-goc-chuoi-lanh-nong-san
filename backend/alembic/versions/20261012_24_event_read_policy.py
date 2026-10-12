"""Avoid recomputing lineage cutoffs for each event held by the current tenant."""

from alembic import op

revision = "20261012_24"
down_revision = "20261012_23"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP POLICY events_read_tenant_or_inspector ON events")
    op.execute("""CREATE POLICY events_read_tenant_or_inspector ON events
    FOR SELECT USING (
      lot_id IN (SELECT public.app_readable_lot_ids())
      AND CASE
        WHEN (SELECT public.app_current_role()) IN ('system_admin', 'inspector')
          OR lot_id IN (
            SELECT id FROM public.lots
            WHERE current_holder_organization_id = (SELECT public.app_current_organization_id())
          )
        THEN true
        ELSE recorded_at <= COALESCE(public.app_event_cutoff(lot_id), 'infinity'::timestamptz)
      END
    )""")


def downgrade():
    op.execute("DROP POLICY events_read_tenant_or_inspector ON events")
    op.execute("""CREATE POLICY events_read_tenant_or_inspector ON events FOR SELECT USING (
      lot_id IN (SELECT public.app_readable_lot_ids())
      AND recorded_at <= COALESCE(public.app_event_cutoff(lot_id), 'infinity'::timestamptz)
    )""")
