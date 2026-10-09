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
    assert script.get_current_head() == "20261009_16"
