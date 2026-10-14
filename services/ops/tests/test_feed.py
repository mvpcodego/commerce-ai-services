import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import create_engine

from ops import config, feed
from ops.celery_app import app
from tests.test_tasks import seed


@pytest.fixture
def eager(db_url, monkeypatch):
    """Celery без брокера: задачи выполняются сразу, chord собирается синхронно."""
    monkeypatch.setattr(app.conf, "task_always_eager", True)
    monkeypatch.setattr(app.conf, "task_eager_propagates", True)
    engine = create_engine(db_url)
    monkeypatch.setattr(feed, "_engine", engine)
    monkeypatch.setattr(config, "SITE_URL", "https://tmgoods.ru")
    yield
    engine.dispose()


async def test_feed_is_valid_yml(sessions, eager, tmp_path):
    await seed(sessions)
    result = feed.start_feed(str(tmp_path)).get()
    assert result["offers"] == 2  # архивная позиция в фид не идёт
    assert result["parts"] == len(feed.CATEGORIES)

    root = ET.parse(tmp_path / feed.FEED_NAME).getroot()
    assert root.tag == "yml_catalog"
    offers = {o.get("id"): o for o in root.iter("offer")}
    assert set(offers) == {"HU", "FR"}
    hu = offers["HU"]
    assert hu.get("available") == "true"
    assert hu.findtext("url") == "https://tmgoods.ru/shop/product/HU"
    assert hu.findtext("picture") == "https://tmgoods.ru/parts/hu.svg"
    assert hu.findtext("vendor") == "Aurio"
    assert offers["FR"].get("available") == "false"  # остатка нет
    assert offers["FR"].find("picture") is None
    ids = {c.get("id") for c in root.iter("category")}
    assert {o.findtext("categoryId") for o in offers.values()} <= ids


def test_offer_escapes_markup():
    xml = feed.offer_xml({"sku": 'A"&<', "title": "Рамка 9\" <Kia>", "stock": 1, "price_retail": 10}, 2)
    ET.fromstring(xml)  # не падает — значит, экранировано
    assert "&lt;Kia&gt;" in xml
