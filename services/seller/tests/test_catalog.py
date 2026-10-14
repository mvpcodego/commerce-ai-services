def test_kits_for_car(catalog):
    found = catalog.find_kit_for_car("Kia", "Rio")
    assert found["found"] and found["car"] == "Kia Rio"
    assert found["kits"][0]["is_default"]  # комплект по умолчанию первым
    assert all(e["type"] not in {"head_unit", "frame", "wiring", "starter_kit"} for e in found["extras"])


def test_brand_only_is_ambiguous(catalog):
    found = catalog.find_kit_for_car("kia")
    assert not found["found"] and found["ambiguous"] and len(found["cars"]) == 3


def test_unknown_car(catalog):
    assert catalog.find_kit_for_car("Tesla", "Model 3")["found"] is False


def test_order_prices_come_from_catalog(catalog):
    priced = catalog.price_order([{"sku": "kit-22", "quantity": 1}, {"sku": "CAM-003", "quantity": 100}])
    kit = next(k for k in catalog.kits if k["id"] == 22)
    cam = next(p for p in catalog.parts if p["sku"] == "CAM-003")
    assert priced["items"][0]["price"] == kit["price_retail"]
    assert priced["items"][1]["quantity"] == cam["stock"]  # больше остатка не продаём
    assert priced["warnings"]
    assert priced["total"] == kit["price_retail"] + cam["price_retail"] * cam["stock"]


def test_out_of_stock_and_unknown_are_skipped(catalog):
    empty = next(p for p in catalog.parts if p["stock"] == 0)
    priced = catalog.price_order([{"sku": empty["sku"], "quantity": 1}, {"sku": "kit-abc", "quantity": 1}])
    assert priced["items"] == [] and len(priced["warnings"]) == 2
