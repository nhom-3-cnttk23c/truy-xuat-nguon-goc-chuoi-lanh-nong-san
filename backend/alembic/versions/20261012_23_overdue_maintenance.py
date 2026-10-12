"""Expose only the bounded overdue-marker operation to the runtime role."""

from alembic import op
from app.core.config import settings

revision = "20261012_23"
down_revision = "20261012_22"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.app_mark_overdue_handovers(age_hours integer)
    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, public AS $$
    DECLARE changed integer;
    BEGIN
      IF age_hours < 1 OR age_hours > 8760 OR age_hours IS NULL THEN
        RAISE EXCEPTION 'Invalid overdue threshold';
      END IF;
      WITH candidates AS (
        SELECT id FROM public.handovers
        WHERE status='pending' AND overdue_at IS NULL
          AND created_at < statement_timestamp() - make_interval(hours => age_hours)
        ORDER BY created_at, id LIMIT 500 FOR UPDATE SKIP LOCKED
      ), marked AS (
        UPDATE public.handovers h SET overdue_at=statement_timestamp()
        FROM candidates c WHERE h.id=c.id RETURNING h.id
      ) SELECT count(*) INTO changed FROM marked;
      RETURN changed;
    END; $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.app_mark_overdue_handovers(integer) FROM PUBLIC"
    )
    role = op.get_bind().dialect.identifier_preparer.quote(settings.DB_USER)
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.app_mark_overdue_handovers(integer) TO {role}"
    )


def downgrade():
    op.execute("DROP FUNCTION public.app_mark_overdue_handovers(integer)")
