"""Каталог продавца поверх продуктовой матрицы (cars, parts, fitment, kits).

Источник — тот же снимок, что у демо-режима сайта: seed/demo-data.json. Инструменты
возвращают словари, а цены и остатки при оформлении берутся только отсюда: модель
может ошибиться в цифре, счёт клиенту — нет.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parents[3] / "seed" / "demo-data.json"
KIT_PREFIX = "kit-"
IN_KIT = {"head_unit", "frame", "wiring", "starter_kit"}


@dataclass
class Catalog:
    cars: list[dict]
    parts: list[dict]
    fitment: list[dict]
    kits: list[dict]
    orders: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Catalog":
        data = json.loads(Path(path or os.environ.get("CATALOG_JSON") or DEFAULT_DATA).read_text("utf-8"))
        return cls(data["cars"], data["parts"], data["fitment"], data["kits"])

    def __post_init__(self) -> None:
        self._part_by_id = {p["id"]: p for p in self.parts}
        self._part_by_sku = {p["sku"]: p for p in self.parts}
        self._kit_by_id = {k["id"]: k for k in self.kits}

    def _cars_like(self, make: str, model: str | None) -> list[dict]:
        make, model = make.strip().lower(), (model or "").strip().lower()
        return [c for c in self.cars if make in c["make"].lower() and (not model or model in c["model"].lower())]

    def _kit_view(self, kit: dict) -> dict:
        head = self._part_by_id[kit["head_unit_id"]]
        return {
            "sku": f"{KIT_PREFIX}{kit['id']}",
            "title": kit["title"],
            "head_unit": head["title"],
            "head_unit_specs": head["specs"],
            "head_unit_stock": head["stock"],
            "frame": self._part_by_id[kit["frame_id"]]["title"],
            "wiring": self._part_by_id[kit["wiring_id"]]["title"],
            "price_retail": kit["price_retail"],
            "is_default": kit["is_default"],
        }

    def popular_models(self, car_make: str) -> dict:
        models = [
            {"model": c["model"], "generation": c["generation"], "slug": c["slug"]}
            for c in self._cars_like(car_make, None)
        ]
        return {"make": car_make, "models": sorted(models, key=lambda m: m["model"])}

    def find_kit_for_car(self, car_make: str, car_model: str | None = None) -> dict:
        cars = self._cars_like(car_make, car_model)
        if not cars:
            return {"found": False, "hint": "Такого авто в справочнике нет. Уточни марку и модель."}
        # Несколько совпадений без модели — пусть агент уточнит, а не выбирает за клиента.
        if len(cars) > 1 and not car_model:
            return {"found": False, "ambiguous": True, "cars": [f"{c['make']} {c['model']}" for c in cars]}

        car = cars[0]
        kits = sorted(
            (self._kit_view(k) for k in self.kits if k["car_id"] == car["id"]),
            key=lambda k: (not k["is_default"], k["price_retail"]),
        )
        fitting = {f["part_id"] for f in self.fitment if f["car_id"] == car["id"]}
        extras = [
            {
                "sku": p["sku"],
                "title": p["title"],
                "type": p["type"],
                "price_retail": p["price_retail"],
                "stock": p["stock"],
            }
            for p in self.parts
            if p["id"] in fitting and p["type"] not in IN_KIT and not p.get("archived")
        ]
        return {"found": True, "car": f"{car['make']} {car['model']}", "kits": kits, "extras": extras}

    def search_products(self, query: str, type: str | None = None, limit: int = 10) -> dict:
        q = query.strip().lower()
        found = [
            {
                "sku": p["sku"],
                "title": p["title"],
                "type": p["type"],
                "brand": p.get("brand"),
                "price_retail": p["price_retail"],
                "stock": p["stock"],
            }
            for p in self.parts
            if not p.get("archived")
            and (not type or p["type"] == type)
            and any(q in str(p.get(f) or "").lower() for f in ("title", "sku", "brand"))
        ]
        return {"query": query, "products": found[: min(limit, 25)]}

    def product_detail(self, sku: str) -> dict:
        part = self._part_by_sku.get(sku)
        return {"product": part} if part else {"error": f"Позиции {sku} нет в каталоге"}

    def fitting_cars(self, sku: str) -> dict:
        part = self._part_by_sku.get(sku)
        if not part:
            return {"error": f"Позиции {sku} нет в каталоге"}
        car_ids = {f["car_id"] for f in self.fitment if f["part_id"] == part["id"]}
        cars = [f"{c['make']} {c['model']} {c['generation']}" for c in self.cars if c["id"] in car_ids]
        return {"part": part["title"], "cars": cars}

    def price_order(self, items: list[dict]) -> dict:
        """Состав заказа по ценам и остаткам каталога. Ничего не сохраняет."""
        lines, warnings = [], []
        for raw in items:
            sku, quantity = str(raw.get("sku", "")), max(1, int(raw.get("quantity") or 1))
            if sku.startswith(KIT_PREFIX):
                kit = self._kit_by_id.get(int(sku[len(KIT_PREFIX) :]) if sku[len(KIT_PREFIX) :].isdigit() else -1)
                if not kit:
                    warnings.append(f"Комплект {sku} не найден, пропущен")
                    continue
                if self._part_by_id[kit["head_unit_id"]]["stock"] <= 0:
                    warnings.append(f"«{kit['title']}» сейчас нет в наличии")
                    continue
                lines.append({"sku": sku, "title": kit["title"], "price": kit["price_retail"], "quantity": quantity})
                continue
            part = self._part_by_sku.get(sku)
            if not part:
                warnings.append(f"Позиция {sku} не найдена, пропущена")
                continue
            if part["stock"] <= 0:
                warnings.append(f"«{part['title']}» нет в наличии")
                continue
            qty = min(quantity, part["stock"])
            if qty < quantity:
                warnings.append(f"«{part['title']}»: в наличии {part['stock']}, поставили столько")
            lines.append({"sku": sku, "title": part["title"], "price": part["price_retail"] or 0, "quantity": qty})
        return {"items": lines, "total": sum(i["price"] * i["quantity"] for i in lines), "warnings": warnings}

    def save_order(self, priced: dict, customer: dict) -> dict:
        order = {"id": len(self.orders) + 1, **priced, "customer": customer, "status": "new"}
        self.orders.append(order)
        return order
