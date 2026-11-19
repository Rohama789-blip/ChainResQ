# ChainResQ - Multi-Agent Supply Chain Crisis Management

An agent team that analyses a supply chain disruption (supplier failure, shipment delay, demand surge),
quantifies impact, finds alternative suppliers, optimises logistics and recommends a recovery strategy.

🌐 Live Demo: https://chain-res-q.vercel.app/

## Problem
Logistics companies face shipment delays, supplier failures and inventory shortages. Manual analysis is slow,
so stock-outs and missed orders happen before a recovery plan exists.

## Architecture (LangGraph state graph)
```
Disruption ─► Disruption Analyst ──(invalid input)──► END
                    │
              Impact Assessor ──(no material impact)──► END
                    │
              Sourcing Agent ─► Logistics Optimizer ─► Strategy Agent ─► Report Agent ─► UI/API
```

| Agent | Responsibility | Tools |
|---|---|---|
| Disruption Analyst | Validates and classifies the event, fills missing data with flagged assumptions | `data_tools` (suppliers, shipments, inventory) |
| Impact Assessor | Stock-out date, shortfall, inbound lost, orders at risk, risk level | `data_tools` |
| Sourcing Agent | Ranks alternative suppliers; allocates volume under capacity/lead-time limits | `optimization.allocate_sourcing` |
| Logistics Optimizer | Evaluates air/road/sea reroutes for delayed shipments | `optimization.reroute_options` |
| Strategy Agent | Builds 3 strategies (Fast / Balanced / Cost-Minimal), scores them, urgency-aware weights | `optimization.score_strategy`, `cover_orders` |
| Report Agent | Action plan + optional Claude executive summary | Anthropic API (optional) |

## Handling unexpected scenarios
- Unknown supplier/shipment/product -> workflow stops with a clear warning.
- Missing `delay_days` / `demand_multiplier` -> assumption applied and flagged.
- No alternative supplier or insufficient capacity -> warning + safety-stock/priority fallback.
- No material impact -> early exit. LLM unavailable -> deterministic report.

## Run
```bash
python -m venv .venv && .venv\Scripts\activate      # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env                                  # optional: add ANTHROPIC_API_KEY
uvicorn backend.api:app --reload                      # open http://127.0.0.1:8000
```
CLI demo: `python -m graph.workflow`   |   Tests: `pytest`
