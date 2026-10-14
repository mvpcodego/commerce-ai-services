"""Порт lib/analytics/procurement.ts. Логика обязана совпадать с оригиналом —
это проверяет tests/test_procurement.py, прогоняя обе версии на одних данных.

Главное — раскрытие комплектов: строка заказа «kit-47» со склада уносит четыре
позиции (ГУ, рамка, проводка, стартовый набор). Без раскрытия продаж по складским
позициям не видно вовсе.
"""

import math
from collections import defaultdict
from typing import Any

STATES = {
    "out": ("Нет на складе", "Позицию покупают, а остатка нет. Каждый день без неё — отказ клиенту."),
    "critical": ("Кончается", "Запаса меньше, чем идёт поставка. Заказывать сейчас, иначе будет разрыв."),
    "low": ("На исходе", "Запаса не хватит на весь горизонт планирования. Ставить в ближайшую заявку."),
    "ok": ("В норме", "Запаса достаточно на горизонт планирования."),
    "idle": ("Не продаётся", "Остаток есть, спроса за период нет. Деньги стоят на полке."),
}
SORT_ORDER = ["out", "critical", "low", "idle", "ok"]


def consumption(orders: list[dict], kits: list[dict], parts: list[dict]) -> dict[str, int]:
    part_by_id = {p["id"]: p for p in parts}
    kit_parts: dict[int, list[str]] = {}
    for kit in kits:
        ids = [kit.get(k) for k in ("head_unit_id", "frame_id", "wiring_id", "starter_kit_id")]
        kit_parts[kit["id"]] = [part_by_id[i]["sku"] for i in ids if i and i in part_by_id]

    sold: dict[str, int] = defaultdict(int)
    for order in orders:
        # Отменённый заказ склад не покидал — спросом он тоже не является.
        if order["status"] == "cancelled":
            continue
        for item in order.get("items") or []:
            sku, qty = item["sku"], item["quantity"]
            kit_id = _kit_id(sku)
            if kit_id is not None:
                for part_sku in kit_parts.get(kit_id, []):
                    sold[part_sku] += qty
            else:
                sold[sku] += qty
    return dict(sold)


def _kit_id(sku: str) -> int | None:
    # Как Number() в оригинале: «kit-» без числа — не комплект и не позиция.
    if not sku.startswith("kit-"):
        return None
    rest = sku[4:].strip()
    try:
        return int(rest) if rest else 0
    except ValueError:
        return None


def _state(stock: int, sold: int, days_left: int | None, lead: int, horizon: int) -> str:
    if sold == 0:
        return "idle" if stock > 0 else "ok"
    if stock <= 0:
        return "out"
    if days_left is None:
        return "ok"
    if days_left <= lead:
        return "critical"
    if days_left <= lead + horizon:
        return "low"
    return "ok"


def _round2(x: float) -> float:
    # Math.round(x * 100) / 100: половина округляется вверх, а не к чётному.
    return math.floor(x * 100 + 0.5) / 100


def plan(
    orders: list[dict], kits: list[dict], parts: list[dict], *, days: int = 90, lead: int = 14, horizon: int = 30
) -> list[dict[str, Any]]:
    sold = consumption(orders, kits, parts)
    rows = []
    for part in parts:
        if part.get("archived"):
            continue
        count = sold.get(part["sku"], 0)
        per_day = count / days
        days_left = math.floor(part["stock"] / per_day) if per_day > 0 else None
        need = math.ceil(per_day * (lead + horizon))
        rows.append(
            {
                "sku": part["sku"],
                "title": part["title"],
                "type": part["type"],
                "stock": part["stock"],
                "sold": count,
                "perDay": _round2(per_day),
                "daysLeft": days_left,
                "reorder": max(0, need - part["stock"]),
                "state": _state(part["stock"], count, days_left, lead, horizon),
            }
        )
    # Сортировка устойчивая, как Array.sort в V8: равные остаются в порядке parts.
    rows.sort(key=lambda r: (SORT_ORDER.index(r["state"]), -r["sold"]))
    return rows


def summarize(rows: list[dict], parts: list[dict]) -> list[dict[str, Any]]:
    price = {p["sku"]: p.get("price_retail") or 0 for p in parts}
    groups: dict[str, dict[str, int]] = {}
    for row in rows:
        g = groups.setdefault(row["state"], {"positions": 0, "units": 0, "amount": 0})
        g["positions"] += 1
        g["units"] += row["reorder"]
        g["amount"] += row["reorder"] * price.get(row["sku"], 0)
    return [
        {"key": key, "label": label, "hint": hint, **groups[key]}
        for key, (label, hint) in STATES.items()
        if key in groups
    ]
