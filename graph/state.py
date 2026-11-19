from typing import Any, Dict, List, Optional, TypedDict


class ChainState(TypedDict, total=False):
    disruption: Dict[str, Any]       # raw input: type, supplier_id / shipment_id / product, delay_days...
    scope: Dict[str, Any]            # resolved by Disruption Analyst
    abort: bool                      # stop workflow early (unusable input)
    impact: Dict[str, Any]           # inventory + orders at risk
    sourcing: Dict[str, Any]         # alternative suppliers + allocations
    logistics: Dict[str, Any]        # reroute options for shipments
    strategies: List[Dict[str, Any]]
    recommendation: Optional[Dict[str, Any]]
    report: str
    warnings: List[str]
    trace: List[str]
