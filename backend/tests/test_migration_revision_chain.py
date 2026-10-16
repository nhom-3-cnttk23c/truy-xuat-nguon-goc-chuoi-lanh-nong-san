from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_legacy_revision_08_precedes_harvest_schema_and_handover_migrations():
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config()
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    script = ScriptDirectory.from_config(config)

    legacy_release = script.get_revision("20261007_08")
    harvest_schema = script.get_revision("20261008_15")
    handover_flow = script.get_revision("20261007_09")

    assert legacy_release.down_revision == "20261007_07"
    assert harvest_schema.down_revision == "20261007_08"
    assert handover_flow.down_revision == "20261008_15"
    recall_orders = script.get_revision("20261015_25")
    assert recall_orders.down_revision == "20261012_24"
    shipments = script.get_revision("20261016_26")
    assert shipments.down_revision == "20261015_25"
    assert script.get_current_head() == "20261016_26"
