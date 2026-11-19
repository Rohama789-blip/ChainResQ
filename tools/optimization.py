"""Optimisation tools: sourcing allocation, shipment rerouting, strategy scoring."""
from typing import Dict, List

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
MODE_OPTIONS = {  # mode: (eta multiplier, cost multiplier)
    "Air": (0.25, 3.2), "Road": (0.6, 1.6), "Sea": (1.0, 1.0),
}


def allocate_sourcing(needed_qty: float, candidates: List[Dict], horizon_days: int,
                      speed_factor: float = 1.0, cost_factor: float = 1.0) -> Dict:
    """Greedy allocation minimising reliability-adjusted cost under capacity/lead-time limits."""
    if needed_qty <= 0:
        return {"allocations": [], "filled_qty": 0, "unfilled_qty": 0, "total_cost": 0.0, "fastest_days": 0}
    ranked = sorted(candidates, key=lambda s: (s["unit_cost"] * cost_factor) / s["reliability"]
                    + 0.02 * s["lead_time_days"] * speed_factor)
    remaining, allocs = needed_qty, []
    for s in ranked:
        lead = round(s["lead_time_days"] * speed_factor, 1)
        if lead >= horizon_days or remaining <= 0:
            continue
        capacity = s["capacity_per_week"] * (horizon_days - lead) / 7 * s["reliability"]
        qty = int(min(remaining, capacity))
        if qty <= 0:
            continue
        allocs.append({"supplier_id": s["supplier_id"], "name": s["name"], "qty": qty, "lead_days": lead,
                       "unit_cost": round(s["unit_cost"] * cost_factor, 2),
                       "cost": round(qty * s["unit_cost"] * cost_factor, 2), "reliability": s["reliability"]})
        remaining -= qty
    return {"allocations": allocs, "filled_qty": int(needed_qty - remaining), "unfilled_qty": int(remaining),
            "total_cost": round(sum(a["cost"] for a in allocs), 2),
            "fastest_days": min((a["lead_days"] for a in allocs), default=0)}


def reroute_options(shipment: Dict, urgency_days: float) -> List[Dict]:
    """Evaluate transport modes for a delayed/at-risk shipment."""
    out = []
    for mode, (eta_m, cost_m) in MODE_OPTIONS.items():
        eta = round(max(1, shipment["eta_days"] * eta_m), 1)
        out.append({"shipment_id": shipment["shipment_id"], "mode": mode, "eta_days": eta,
                    "cost": round(shipment["cost"] * cost_m, 2),
                    "extra_cost": round(shipment["cost"] * (cost_m - 1), 2),
                    "meets_deadline": eta <= urgency_days})
    if any(o["meets_deadline"] for o in out):
        return sorted(out, key=lambda o: (not o["meets_deadline"], o["cost"]))
    return sorted(out, key=lambda o: o["eta_days"])  # nothing meets the deadline: fastest first


def cover_orders(orders: List[Dict], available_qty: float) -> List[Dict]:
    """Protect orders by priority then due date until supply runs out."""
    protected, left = [], available_qty
    for o in sorted(orders, key=lambda o: (PRIORITY_RANK.get(o["priority"], 3), o["due_in_days"])):
        if o["qty"] <= left:
            protected.append(o)
            left -= o["qty"]
    return protected


def score_strategy(s: Dict, max_cost: float, max_days: float, urgent: bool) -> float:
    w_f, w_c, w_t = (0.60, 0.10, 0.30) if urgent else (0.70, 0.15, 0.15)
    service = 0.5 * s["fulfilment_pct"] + 0.5 * s["orders_protected_pct"]
    return round(w_f * service / 100
                 + w_c * (1 - s["est_cost"] / max_cost if max_cost else 1)
                 + w_t * (1 - s["recovery_days"] / max_days if max_days else 1), 3)
