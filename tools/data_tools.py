"""Data access tools used by agents (CSV-backed; swap for DB/ERP/TMS APIs in production)."""
import csv
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _cast(v: str):
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v


def load_csv(name: str) -> List[Dict]:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: _cast(v) for k, v in row.items()} for row in csv.DictReader(f)]


def get_supplier(supplier_id: str) -> Optional[Dict]:
    return next((s for s in load_csv("suppliers.csv") if s["supplier_id"] == supplier_id), None)


def get_shipment(shipment_id: str) -> Optional[Dict]:
    return next((s for s in load_csv("shipments.csv") if s["shipment_id"] == shipment_id), None)


def active_shipments(product: Optional[str] = None, supplier_id: Optional[str] = None) -> List[Dict]:
    rows = [s for s in load_csv("shipments.csv") if s["status"] != "Delivered"]
    if product:
        rows = [s for s in rows if s["product"] == product]
    if supplier_id:
        rows = [s for s in rows if s["supplier_id"] == supplier_id]
    return rows


def inventory_for_product(product: str) -> List[Dict]:
    return [i for i in load_csv("inventory.csv") if i["product"] == product]


def orders_for_product(product: str) -> List[Dict]:
    return [o for o in load_csv("orders.csv") if o["product"] == product]


def alternative_suppliers(product: str, exclude_id: Optional[str] = None) -> List[Dict]:
    return [s for s in load_csv("suppliers.csv")
            if s["product"] == product and s["supplier_id"] != exclude_id and s["status"] == "Active"]


def known_products() -> List[str]:
    return sorted({s["product"] for s in load_csv("suppliers.csv")})
