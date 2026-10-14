"""Данные агента: каталог и заказы из снимка проекта, расчёт — функция ops.

Логику закупок агент не дублирует: берёт ops.procurement.plan — ту самую, что считает
раздел «Закупки» и фоновая задача ops (её совпадение с TS-оригиналом проверено тестами ops).
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services" / "ops"))  # пакет ops не устанавливается, берём исходник

from ops.procurement import plan, summarize

DATA = ROOT / "seed" / "demo-data.json"


def load(path: Path = DATA) -> dict:
    return json.loads(path.read_text("utf-8"))


def reorder_plan(data: dict, *, days: int = 90, lead: int = 14, horizon: int = 30) -> dict:
    """Что заказать. Окно спроса считается от последнего заказа в данных, а не от сегодня:
    демо-снимок не обновляется, и «последние 90 дней» от текущей даты были бы пустыми."""
    moments = [datetime.fromisoformat(o["created_at"]) for o in data["orders"]]
    since = max(moments) - timedelta(days=days)
    recent = [o for o, at in zip(data["orders"], moments, strict=True) if at >= since]
    rows = plan(recent, data["kits"], data["parts"], days=days, lead=lead, horizon=horizon)
    price = {p["sku"]: p.get("price_retail") or 0 for p in data["parts"]}
    to_order = [
        {
            **{k: r[k] for k in ("sku", "title", "stock", "sold", "daysLeft", "reorder", "state")},
            "amount": r["reorder"] * price[r["sku"]],
        }
        for r in rows
        if r["reorder"] > 0
    ]
    return {
        "window_days": days,
        "lead_days": lead,
        "horizon_days": horizon,
        "summary": summarize(rows, data["parts"]),
        "to_order": to_order,
    }
