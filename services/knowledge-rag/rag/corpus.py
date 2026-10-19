"""Корпус базы знаний: карточки автомобилей, магнитол и наборов из seed/demo-data.json + статьи FAQ.

Генерация детерминированная: тот же снимок данных даёт те же документы в том же порядке.
Запуск `uv run python -m rag.corpus` пишет data/corpus.jsonl (для просмотра глазами).
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from rag.faq import FAQ

DEFAULT_DATA = Path(__file__).resolve().parents[3] / "seed" / "demo-data.json"
OUT = Path(__file__).resolve().parents[1] / "data" / "corpus.jsonl"


@dataclass(frozen=True)
class Doc:
    doc_id: str
    doc_type: str  # car | head_unit | bundle | faq
    title: str
    text: str
    make: str | None = None
    model: str | None = None


def load_seed(path: str | os.PathLike | None = None) -> dict:
    return json.loads(Path(path or os.environ.get("CATALOG_JSON") or DEFAULT_DATA).read_text("utf-8"))


def _rub(v: int) -> str:
    return f"{v:,}".replace(",", " ") + " ₽"


def _yn(v: bool) -> str:
    return "есть" if v else "нет"


def _stock(n: int) -> str:
    return f"в наличии {n} шт" if n > 0 else "нет в наличии, доступна под заказ"


def _car_doc(car: dict, kits: list[dict], parts: dict[int, dict]) -> Doc:
    years = (
        f"{car['year_from']}–{car['year_to']}" if car["year_to"] else f"с {car['year_from']} года по настоящее время"
    )
    name = f"{car['make']} {car['model']}"
    kit0 = next((k for k in kits if k["is_default"]), kits[0])
    frame, wiring, starter = parts[kit0["frame_id"]], parts[kit0["wiring_id"]], parts[kit0["starter_kit_id"]]
    screen = frame["specs"].get("screen")
    can = "с поддержкой CAN-шины" if wiring["specs"].get("canbus") else "без CAN-шины"
    lines = [
        f"Магнитола для {name}: поколение {car['generation']}, годы выпуска {years}, кузов {car['body']}.",
        (
            f"Для установки нужна переходная рамка «{frame['title']}» (артикул {frame['sku']}, цвет "
            f'{frame["specs"].get("color", "чёрный")}, под экран {screen}"), цена {_rub(frame["price_retail"])}.'
        ),
        (
            f"Проводка: «{wiring['title']}» (артикул {wiring['sku']}, {wiring['specs'].get('pins')} pin, {can}), "
            f"цена {_rub(wiring['price_retail'])}."
        ),
        f"Стартовый набор {starter['sku']} включает: {', '.join(starter['specs'].get('includes', []))}.",
        "",
        f"Готовые комплекты для {name} (магнитола + рамка + проводка + стартовый набор):",
    ]
    for k in kits:
        hu = parts[k["head_unit_id"]]
        mark = " — рекомендуемый комплект" if k["is_default"] else ""
        lines.append(
            f"Комплект «{k['title']}» стоит {_rub(k['price_retail'])}, магнитола {hu['sku']}, "
            f"уровень «{hu['specs']['tier']}»{mark}."
        )
    return Doc(
        f"car-{car['slug']}", "car", f"Магнитола и комплекты для {name}", "\n".join(lines), car["make"], car["model"]
    )


def _hu_doc(hu: dict, cars: list[dict]) -> Doc:
    s = hu["specs"]
    form = " 2DIN" if s.get("din") == 2 else (", вертикальный (портретный) экран" if s.get("portrait") else "")
    extras = []
    if s.get("qled"):
        extras.append("QLED-матрица")
    if s.get("cam360"):
        extras.append("поддержка камер кругового обзора 360° (cam360)")
    text = (
        f"Магнитола {hu['title']} бренда {hu['brand']}, серия {hu['series']}, уровень «{s['tier']}». "
        f'Диагональ экрана {s["screen"]}" (дюймов){form}. Процессор {s["cores"]} ядер, оперативная память {s["ram"]} ГБ, '
        f"встроенная память {s['rom']} ГБ.\n\n"
        f"DSP-процессор звука: {_yn(s.get('dsp'))}. GPS: {_yn(s.get('gps'))}. Wi-Fi: {_yn(s.get('wifi'))}. "
        f"Встроенный 4G LTE модем: {_yn(s.get('lte'))}."
        + (f" Дополнительно: {', '.join(extras)}." if extras else "")
        + f"\n\nЦена {_rub(hu['price_retail'])}, {_stock(hu['stock'])}. Артикул {hu['sku']}."
    )
    if cars:
        text += " Входит в готовые комплекты для автомобилей: " + ", ".join(cars) + "."
    return Doc(hu["sku"].lower(), "head_unit", f"Магнитола {hu['title']}", text)


def _bundle_doc(b: dict, by_sku: dict[str, dict]) -> Doc:
    items = [f"{by_sku[i['sku']]['title'] if i['sku'] in by_sku else i['sku']} × {i['quantity']}" for i in b["items"]]
    text = (
        f"Набор «{b['title']}» (артикул {b['sku']}, раздел «{b['category']}»). Состав набора: {'; '.join(items)}. "
        f"Цена набора {_rub(b['price_retail'])}, {_stock(b['stock'])}. Набор универсальный и подходит к любому "
        f"автомобилю с магнитолой из каталога."
    )
    return Doc(f"bundle-{b['sku'].lower()}", "bundle", f"Набор {b['title']}", text)


def build_corpus(data: dict | None = None) -> list[Doc]:
    data = data or load_seed()
    parts = {p["id"]: p for p in data["parts"] if not p.get("archived")}
    by_sku = {p["sku"]: p for p in parts.values()}
    cars = {c["id"]: c for c in data["cars"]}
    kits_by_car: dict[int, list[dict]] = {}
    cars_by_hu: dict[int, list[str]] = {}
    for k in sorted(data["kits"], key=lambda k: k["id"]):
        if k["head_unit_id"] not in parts:
            continue
        kits_by_car.setdefault(k["car_id"], []).append(k)
        c = cars[k["car_id"]]
        cars_by_hu.setdefault(k["head_unit_id"], []).append(f"{c['make']} {c['model']}")

    docs = [_car_doc(c, kits_by_car[c["id"]], parts) for c in data["cars"] if c["id"] in kits_by_car]
    docs += [_hu_doc(p, cars_by_hu.get(p["id"], [])) for p in parts.values() if p["type"] == "head_unit"]
    docs += [_bundle_doc(b, by_sku) for b in data["bundles"]]
    docs += [Doc(doc_id, "faq", title, text) for doc_id, title, text in FAQ]
    return docs


def main() -> None:
    docs = build_corpus()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("".join(json.dumps(asdict(d), ensure_ascii=False) + "\n" for d in docs), "utf-8")
    counts: dict[str, int] = {}
    for d in docs:
        counts[d.doc_type] = counts.get(d.doc_type, 0) + 1
    print(f"{len(docs)} документов → {OUT}: {counts}")


if __name__ == "__main__":
    main()
