"""FastAPI backend. Run from project root:  uvicorn backend.api:app --reload"""
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from graph.workflow import HAS_LANGGRAPH, run_workflow
from tools import data_tools as dt

load_dotenv()
app = FastAPI(title="ChainResQ API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SCENARIOS = [
    {"id": "sf", "label": "Supplier failure - Guangdong Circuits (S03)",
     "payload": {"type": "supplier_failure", "supplier_id": "S03", "severity": "high"}},
    {"id": "sd", "label": "Shipment delay - SH104 Battery Packs (+12 days)",
     "payload": {"type": "shipment_delay", "shipment_id": "SH104", "delay_days": 12}},
    {"id": "is", "label": "Demand surge - Sensors (1.8x)",
     "payload": {"type": "inventory_shortage", "product": "Sensors", "demand_multiplier": 1.8}},
    {"id": "bad", "label": "Bad input - unknown supplier (error handling demo)",
     "payload": {"type": "supplier_failure", "supplier_id": "S99"}},
]


class Disruption(BaseModel):
    type: str
    supplier_id: Optional[str] = None
    shipment_id: Optional[str] = None
    product: Optional[str] = None
    delay_days: Optional[int] = None
    demand_multiplier: Optional[float] = None
    severity: Optional[str] = "medium"


@app.get("/api/health")
def health():
    return {"status": "ok", "langgraph": HAS_LANGGRAPH}


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


@app.get("/api/data/{name}")
def data(name: str):
    if name not in {"suppliers", "inventory", "shipments", "orders"}:
        raise HTTPException(404, "Unknown dataset")
    return dt.load_csv(f"{name}.csv")


@app.post("/api/analyze")
def analyze(d: Disruption):
    try:
        out = run_workflow(d.model_dump(exclude_none=True))
    except Exception as e:  # never crash the UI
        raise HTTPException(500, f"Workflow error: {e}")
    return out


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
