"""Agent nodes. Each takes the shared ChainState and returns a partial state update."""
import os
from typing import Dict

from graph.state import ChainState
from tools import data_tools as dt
from tools import optimization as opt

HORIZON_DAYS = 30


def _log(state: ChainState, agent: str, msg: str):
    return list(state.get("trace", [])) + [f"[{agent}] {msg}"]


def _warn(state: ChainState, msg: str):
    return list(state.get("warnings", [])) + [msg]


# 1 ------------------------------------------------------------------ Disruption Analyst
def disruption_analyst(state: ChainState) -> Dict:
    d = dict(state.get("disruption") or {})
    warnings, scope = list(state.get("warnings", [])), {"delay_days": 0, "demand_multiplier": 1.0,
                                                          "lost_supplier": None, "delayed": {}}
    dtype = d.get("type")
    try:
        if dtype == "supplier_failure":
            sup = dt.get_supplier(d.get("supplier_id", ""))
            if not sup:
                raise ValueError(f"Unknown supplier '{d.get('supplier_id')}'")
            scope.update(product=sup["product"], lost_supplier=sup["supplier_id"], supplier_name=sup["name"])
        elif dtype == "shipment_delay":
            sh = dt.get_shipment(d.get("shipment_id", ""))
            if not sh:
                raise ValueError(f"Unknown shipment '{d.get('shipment_id')}'")
            delay = d.get("delay_days")
            if delay is None:
                delay = 10
                warnings.append("delay_days missing - assumed 10 days")
            scope.update(product=sh["product"], delay_days=delay, delayed={sh["shipment_id"]: delay})
        elif dtype == "inventory_shortage":
            if d.get("product") not in dt.known_products():
                raise ValueError(f"Unknown product '{d.get('product')}'")
            mult = d.get("demand_multiplier")
            if mult is None:
                mult = 1.5
                warnings.append("demand_multiplier missing - assumed 1.5x surge")
            scope.update(product=d["product"], demand_multiplier=float(mult))
        else:
            raise ValueError(f"Unsupported disruption type '{dtype}'")
    except (ValueError, FileNotFoundError) as e:
        warnings.append(f"Input rejected: {e}")
        return {"abort": True, "warnings": warnings,
                "trace": _log(state, "DisruptionAnalyst", f"aborted - {e}")}
    scope["type"] = dtype
    scope["severity"] = d.get("severity", "medium")
    return {"scope": scope, "abort": False, "warnings": warnings,
            "trace": _log(state, "DisruptionAnalyst", f"{dtype} on '{scope['product']}' classified")}


# 2 ------------------------------------------------------------------ Impact Assessor
def impact_assessor(state: ChainState) -> Dict:
    sc = state["scope"]
    inv = dt.inventory_for_product(sc["product"])
    on_hand = sum(i["on_hand"] for i in inv)
    daily = sum(i["daily_demand"] for i in inv) * sc["demand_multiplier"]
    inbound_ok, inbound_lost, affected = 0, 0, []
    for s in dt.active_shipments(product=sc["product"]):
        eta = s["eta_days"] + sc["delayed"].get(s["shipment_id"], 0)
        failed = s["supplier_id"] == sc["lost_supplier"]
        if failed or eta > HORIZON_DAYS:
            inbound_lost += s["qty"]
            affected.append({**s, "adj_eta": eta, "reason": "supplier failure" if failed else f"delayed to day {eta}"})
        else:
            inbound_ok += s["qty"]
    demand_h = daily * HORIZON_DAYS
    supply = on_hand + inbound_ok
    shortfall = max(0, round(demand_h - supply))
    stockout = round(supply / daily, 1) if daily else 999
    orders = dt.orders_for_product(sc["product"])
    at_risk = [o for o in orders if o["due_in_days"] > stockout]
    if not inv:
        state_warn = _warn(state, f"No inventory rows for {sc['product']} - impact estimated from shipments only")
    else:
        state_warn = state.get("warnings", [])
    recovery_qty = max(shortfall, sum(o["qty"] for o in at_risk))
    level = "CRITICAL" if stockout < 10 else "HIGH" if stockout < 20 else "MEDIUM" if shortfall else "LOW"
    impact = {"product": sc["product"], "on_hand": on_hand, "daily_demand": round(daily, 1),
              "inbound_ok": inbound_ok, "inbound_lost": inbound_lost, "stockout_days": stockout,
              "shortfall_qty": shortfall, "recovery_qty": recovery_qty, "demand_horizon": round(demand_h), "supply_base": supply,
              "affected_shipments": affected, "orders_at_risk": at_risk, "risk_level": level}
    if shortfall == 0 and not affected:
        return {"impact": impact, "abort": True, "warnings": state_warn,
                "trace": _log(state, "ImpactAssessor", "no material impact - workflow ends")}
    return {"impact": impact, "warnings": state_warn,
            "trace": _log(state, "ImpactAssessor", f"risk={level}, stock-out in {stockout}d, "
                                                   f"shortfall={shortfall}, {len(at_risk)} orders at risk")}


# 3 ------------------------------------------------------------------ Sourcing Agent
def sourcing_agent(state: ChainState) -> Dict:
    sc, imp = state["scope"], state["impact"]
    candidates = dt.alternative_suppliers(sc["product"], exclude_id=sc["lost_supplier"])
    needed = imp["recovery_qty"]
    base = {"candidates": [c["supplier_id"] for c in candidates], "needed": needed}
    plans = {
        "fast": opt.allocate_sourcing(needed, candidates, HORIZON_DAYS, speed_factor=0.5, cost_factor=1.25),
        "balanced": opt.allocate_sourcing(needed, candidates, HORIZON_DAYS),
    }
    warnings = state.get("warnings", [])
    if not candidates:
        warnings = _warn(state, f"No alternative suppliers for {sc['product']} - fallback to stock/priority protection")
    elif plans["balanced"]["unfilled_qty"] > 0:
        warnings = _warn(state, f"Alternative suppliers can fill only {plans['balanced']['filled_qty']}/{needed} units in time")
    return {"sourcing": {**base, "plans": plans}, "warnings": warnings,
            "trace": _log(state, "SourcingAgent", f"{len(candidates)} alternatives; balanced plan fills "
                                                   f"{plans['balanced']['filled_qty']}/{needed}")}


# 4 ------------------------------------------------------------------ Logistics Optimizer
def logistics_optimizer(state: ChainState) -> Dict:
    imp = state["impact"]
    urgency = max(imp["stockout_days"] - 2, 1)
    options = []
    for s in imp["affected_shipments"]:
        if s["reason"] == "supplier failure":
            continue  # cargo cannot be recovered from a failed supplier; handled by sourcing
        options.append({"shipment_id": s["shipment_id"], "qty": s["qty"], "current_eta": s["adj_eta"],
                        "options": opt.reroute_options({**s, "eta_days": s["adj_eta"]}, urgency)})
    return {"logistics": {"urgency_days": urgency, "reroutes": options},
            "trace": _log(state, "LogisticsOptimizer", f"evaluated reroutes for {len(options)} shipment(s)")}


# 5 ------------------------------------------------------------------ Strategy Agent
def strategy_agent(state: ChainState) -> Dict:
    imp, src, log_, sc = state["impact"], state["sourcing"], state["logistics"], state["scope"]
    base_cost = (dt.get_supplier(sc["lost_supplier"]) or {}).get("unit_cost") if sc["lost_supplier"] else None
    if base_cost is None:
        inv = dt.inventory_for_product(sc["product"])
        sup = dt.get_supplier(inv[0]["primary_supplier_id"]) if inv else None
        base_cost = sup["unit_cost"] if sup else 0
    reserve = int(sum(i["reorder_point"] for i in dt.inventory_for_product(sc["product"])) * 0.5)
    at_risk = imp["orders_at_risk"]
    demand_h = imp["demand_horizon"] or 1

    def build(name, plan, reroute_air, desc, extra_supply=0):
        plan_cost = plan["total_cost"] if plan else 0
        new_supply = (plan["filled_qty"] if plan else 0) + extra_supply
        premium = max(0, plan_cost - (plan["filled_qty"] if plan else 0) * base_cost)
        rr_cost, rr_actions = 0, []
        for r in log_["reroutes"]:
            pick = r["options"][0] if reroute_air else next((o for o in r["options"] if o["mode"] != "Air"), r["options"][0])
            rr_cost += pick["extra_cost"]
            rr_actions.append(f"Reroute {r['shipment_id']} via {pick['mode']} (ETA {pick['eta_days']}d)")
        actions = [f"Order {a['qty']} units from {a['name']} ({a['supplier_id']}), lead {a['lead_days']}d"
                   for a in (plan["allocations"] if plan else [])] + rr_actions
        if extra_supply:
            actions.append(f"Release {extra_supply} units of safety stock for High-priority orders")
        protected = opt.cover_orders(at_risk, new_supply)
        days = plan["fastest_days"] if plan and plan["allocations"] else 0
        prot_pct = round(100 * len(protected) / len(at_risk), 1) if at_risk else 100.0
        return {"name": name, "description": desc, "actions": actions,
                "est_cost": round(plan_cost + rr_cost, 2), "premium_cost": round(premium + rr_cost, 2),
                "recovery_days": days, "supply_added": new_supply,
                "fulfilment_pct": round(min(100, 100 * (imp["supply_base"] + new_supply) / demand_h), 1),
                "orders_protected_pct": prot_pct,
                "orders_protected": [o["order_id"] for o in protected],
                "orders_unprotected": [o["order_id"] for o in at_risk if o not in protected]}

    strategies = [
        build("Fast Recovery", src["plans"]["fast"], True, "Expedite everything: air freight + fastest alternative suppliers."),
        build("Balanced Recovery", src["plans"]["balanced"], False, "Alternative suppliers by sea/road, cheapest viable reroutes."),
        build("Cost-Minimal Hold", None, False, "No new sourcing; release safety stock and protect High-priority orders only.",
              extra_supply=reserve),
    ]
    urgent = imp["stockout_days"] < 15
    max_cost = max(s["est_cost"] for s in strategies) or 1
    max_days = max(s["recovery_days"] for s in strategies) or 1
    for s in strategies:
        s["score"] = opt.score_strategy(s, max_cost, max_days, urgent)
    best = max(strategies, key=lambda s: s["score"])
    best["recommended"] = True
    return {"strategies": strategies, "recommendation": best,
            "trace": _log(state, "StrategyAgent", f"recommended '{best['name']}' (score {best['score']}, "
                                                  f"{'urgent' if urgent else 'normal'} weighting)")}


# 6 ------------------------------------------------------------------ Report Agent
def _narrative(text: str) -> str:
    """Optional LLM polish. Falls back to the deterministic report if no key / package / network."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"), max_tokens=500,
                                     messages=[{"role": "user", "content":
                                                "Write a 4-sentence executive summary of this supply chain recovery plan:\n" + text}])
        return msg.content[0].text
    except Exception:
        return ""


def report_agent(state: ChainState) -> Dict:
    imp, rec, sc = state["impact"], state["recommendation"], state["scope"]
    lines = [f"CRISIS REPORT - {sc['type'].replace('_', ' ').title()} ({imp['product']})",
             f"Risk level: {imp['risk_level']} | Stock-out in {imp['stockout_days']} days | Shortfall: {imp['shortfall_qty']} units | Recovery qty: {imp['recovery_qty']}",
             f"Orders at risk: {len(imp['orders_at_risk'])} | Inbound lost/delayed: {imp['inbound_lost']} units",
             "", f"RECOMMENDED: {rec['name']} - {rec['description']}",
             f"  Cost ${rec['est_cost']:,.0f} (premium ${rec['premium_cost']:,.0f}) | Recovery {rec['recovery_days']}d | Supply cover {rec['fulfilment_pct']}% | Orders protected {rec['orders_protected_pct']}%",
             "  Actions:"] + [f"   - {a}" for a in rec["actions"]]
    if rec["orders_unprotected"]:
        lines.append(f"  Customer comms needed for: {', '.join(rec['orders_unprotected'])}")
    if state.get("warnings"):
        lines += ["", "Warnings:"] + [f"  ! {w}" for w in state["warnings"]]
    text = "\n".join(lines)
    summary = _narrative(text)
    return {"report": (summary + "\n\n" if summary else "") + text,
            "trace": _log(state, "ReportAgent", "report generated" + (" (LLM summary)" if summary else ""))}
