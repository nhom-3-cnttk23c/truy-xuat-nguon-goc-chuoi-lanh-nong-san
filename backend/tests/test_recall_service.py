"""Unit test suite for N3-51: Lot recall report and verification against the independent oracle."""

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.schemas.recall import RecallLotItem, RecallReport, RecallSummary


def load_recall_oracle() -> dict:
    oracle_path = Path(__file__).parent / "data/recall-lineage-oracle.json"
    assert oracle_path.exists(), "Oracle file not found"
    return json.loads(oracle_path.read_text(encoding="utf-8"))


def test_recall_oracle_matches_r1_specifications():
    """Verify that R1 recall calculation in oracle matches business rules."""
    oracle = load_recall_oracle()
    r1 = oracle["root_lots"]["R1"]

    descendants = r1["descendants"]
    assert len(descendants) == 8

    # Check consumed and recoverable math
    recoverable_sum = sum(
        Decimal(d["remaining_quantity"]) for d in descendants if d["status"] == "active"
    )
    assert recoverable_sum == Decimal("140.000")

    consumed_sum = sum(
        Decimal(d["consumed_quantity"])
        for d in descendants
        if d["status"] == "consumed"
    )
    assert consumed_sum == Decimal("60.000")

    # Check summary
    summary = r1["summary"]
    assert summary["total_descendants_count"] == 8
    assert Decimal(summary["total_recoverable_kg"]) == recoverable_sum
    assert Decimal(summary["total_consumed_kg"]) == consumed_sum
    assert summary["involved_organizations_count"] == 3
    assert summary["has_multi_source_merge"] is True
    assert summary["has_consumed_lot"] is True


def test_recall_oracle_matches_r3_specifications():
    """Verify that R3 (no consumed lots) matches business rules."""
    oracle = load_recall_oracle()
    r3 = oracle["root_lots"]["R3"]

    descendants = r3["descendants"]
    assert len(descendants) == 8

    recoverable_sum = sum(
        Decimal(d["remaining_quantity"]) for d in descendants if d["status"] == "active"
    )
    assert recoverable_sum == Decimal("200.000")

    consumed_sum = sum(
        Decimal(d["consumed_quantity"])
        for d in descendants
        if d["status"] == "consumed"
    )
    assert consumed_sum == Decimal("0.000")

    summary = r3["summary"]
    assert summary["total_descendants_count"] == 8
    assert Decimal(summary["total_recoverable_kg"]) == Decimal("200.000")
    assert Decimal(summary["total_consumed_kg"]) == Decimal("0.000")
    assert summary["has_consumed_lot"] is False


def test_recall_schemas_validation():
    """Verify that Pydantic models validate and serialize correctly."""
    root_id = uuid4()
    child_id = uuid4()

    root_item = RecallLotItem(
        id=root_id,
        lot_code="LOT-ROOT-01",
        name="Cà chua cherry — R1",
        tier=1,
        status="closed",
        is_multi_source_merge=False,
        remaining_quantity=Decimal("0.000"),
        consumed_quantity=Decimal("0.000"),
        recoverable_quantity=Decimal("0.000"),
        unit="kg",
    )

    child_item = RecallLotItem(
        id=child_id,
        lot_code="LOT-CHILD-01",
        name="Cà chua cherry — D1",
        tier=4,
        status="active",
        is_multi_source_merge=True,
        remaining_quantity=Decimal("40.000"),
        consumed_quantity=Decimal("0.000"),
        recoverable_quantity=Decimal("40.000"),
        unit="kg",
        parent_lot_ids=[root_id],
    )

    summary = RecallSummary(
        root_lot_id=root_id,
        root_lot_code="LOT-ROOT-01",
        root_lot_name="Cà chua cherry — R1",
        initial_quantity=Decimal("100.000"),
        unit="kg",
        total_affected_lots=2,
        total_descendants_count=1,
        total_recoverable_kg=Decimal("40.000"),
        total_consumed_kg=Decimal("0.000"),
        involved_organizations_count=2,
        involved_organizations=["Hợp tác xã rau sạch", "Trang trại mẫu"],
        has_multi_source_merge=True,
        has_consumed_lot=False,
    )

    report = RecallReport(
        root_lot=root_item,
        summary=summary,
        descendants=[child_item],
        affected_lots=[root_item, child_item],
    )

    dumped = report.model_dump()
    assert dumped["root_lot"]["id"] == root_id
    assert len(dumped["descendants"]) == 1
    assert dumped["summary"]["total_recoverable_kg"] == Decimal("40.000")
    assert dumped["summary"]["has_multi_source_merge"] is True
