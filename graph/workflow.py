"""Workflow: LangGraph state graph (falls back to an equivalent sequential runner if langgraph is absent)."""
from agents import nodes
from graph.state import ChainState

try:
    from langgraph.graph import END, StateGraph
    HAS_LANGGRAPH = True
except ImportError:  # keeps project runnable/testable without the dependency
    HAS_LANGGRAPH = False

ORDER = ["disruption_analyst", "impact_assessor", "sourcing_agent",
         "logistics_optimizer", "strategy_agent", "report_agent"]


def _route(state: ChainState) -> str:
    """Adaptive branch: stop early on unusable input or no material impact."""
    return "stop" if state.get("abort") else "continue"


def build_graph():
    g = StateGraph(ChainState)
    for name in ORDER:
        g.add_node(name, getattr(nodes, name))
    g.set_entry_point("disruption_analyst")
    for a, b in zip(ORDER[1:-1], ORDER[2:]):
        g.add_edge(a, b)
    for gate, nxt in (("disruption_analyst", "impact_assessor"), ("impact_assessor", "sourcing_agent")):
        g.add_conditional_edges(gate, _route, {"continue": nxt, "stop": END})
    g.add_edge("report_agent", END)
    return g.compile()


def _run_sequential(state: ChainState) -> ChainState:
    for name in ORDER:
        state = {**state, **getattr(nodes, name)(state)}
        if name in ("disruption_analyst", "impact_assessor") and state.get("abort"):
            break
    return state


def run_workflow(disruption: dict) -> ChainState:
    init: ChainState = {"disruption": disruption, "warnings": [], "trace": [], "abort": False}
    final = build_graph().invoke(init) if HAS_LANGGRAPH else _run_sequential(init)
    if "report" not in final:
        final["report"] = "No action plan generated.\n" + "\n".join(final.get("warnings", ["No material impact."]))
    return final


if __name__ == "__main__":
    import json
    out = run_workflow({"type": "supplier_failure", "supplier_id": "S03"})
    print("\n".join(out["trace"])); print(); print(out["report"])
