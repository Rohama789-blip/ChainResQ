import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.workflow import run_workflow
from tools.optimization import allocate_sourcing, cover_orders


def test_supplier_failure_gives_recommendation():
    out = run_workflow({"type": "supplier_failure", "supplier_id": "S03"})
    assert out["impact"]["inbound_lost"] == 16000
    assert out["recommendation"]["orders_protected_pct"] == 100.0
    assert len(out["strategies"]) == 3 and out["report"]


def test_shipment_delay_includes_reroute():
    out = run_workflow({"type": "shipment_delay", "shipment_id": "SH104", "delay_days": 12})
    assert out["logistics"]["reroutes"]


def test_missing_delay_uses_assumption_and_warns():
    out = run_workflow({"type": "shipment_delay", "shipment_id": "SH104"})
    assert any("assumed" in w for w in out["warnings"])


def test_unknown_supplier_aborts_gracefully():
    out = run_workflow({"type": "supplier_failure", "supplier_id": "S99"})
    assert out["abort"] and "rejected" in " ".join(out["warnings"]).lower()
    assert "No action plan" in out["report"]


def test_allocation_respects_capacity():
    cands = [{"supplier_id": "X", "name": "X", "lead_time_days": 10, "unit_cost": 1, "capacity_per_week": 700, "reliability": 1.0}]
    res = allocate_sourcing(10_000, cands, horizon_days=30)
    assert res["filled_qty"] <= 700 * 20 / 7 + 1 and res["unfilled_qty"] > 0


def test_cover_orders_prioritises_high():
    orders = [{"order_id": "L", "qty": 10, "priority": "Low", "due_in_days": 1},
              {"order_id": "H", "qty": 10, "priority": "High", "due_in_days": 9}]
    assert [o["order_id"] for o in cover_orders(orders, 10)] == ["H"]
