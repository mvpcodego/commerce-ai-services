import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ops import procurement as calc

ROOT = Path(__file__).resolve().parents[3]
DEMO = json.loads((ROOT / "seed/demo-data.json").read_text())


def ts_plan(params: dict) -> dict:
    out = subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(Path(__file__).parent / "ts_procurement.mts"), json.dumps(params)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="нужен node для эталона")
@pytest.mark.parametrize(
    "params",
    [
        {"days": 90, "leadDays": 14, "horizonDays": 30},
        {"days": 365, "leadDays": 30, "horizonDays": 60},
        {"days": 14, "leadDays": 1, "horizonDays": 7},
    ],
)
def test_matches_typescript(params):
    expected = ts_plan(params)
    rows = calc.plan(DEMO["orders"], DEMO["kits"], DEMO["parts"], days=params["days"], lead=params["leadDays"], horizon=params["horizonDays"])
    assert rows == expected["rows"]
    assert calc.summarize(rows, DEMO["parts"]) == expected["summary"]


def test_kit_is_expanded_into_parts():
    parts = [
        {"id": 1, "sku": "HU", "title": "ГУ", "type": "head_unit", "stock": 0, "price_retail": 100},
        {"id": 2, "sku": "FR", "title": "Рамка", "type": "frame", "stock": 5, "price_retail": 10},
    ]
    kits = [{"id": 7, "head_unit_id": 1, "frame_id": 2, "wiring_id": None, "starter_kit_id": None}]
    orders = [
        {"items": [{"sku": "kit-7", "quantity": 2}], "status": "shipped"},
        {"items": [{"sku": "kit-7", "quantity": 5}], "status": "cancelled"},
    ]
    assert calc.consumption(orders, kits, parts) == {"HU": 2, "FR": 2}
    states = {r["sku"]: r["state"] for r in calc.plan(orders, kits, parts, days=30)}
    assert states == {"HU": "out", "FR": "ok"}  # 5 шт. при 2 за 30 дней — на 75 дней
