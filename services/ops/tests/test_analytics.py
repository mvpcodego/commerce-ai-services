import json
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from ops.analytics import order_lines, revenue_by_month, sync_sales, top_skus

CH_URL = os.environ.get("CLICKHOUSE_TEST_URL")  # http://user:pass@localhost:8123/tmgoods_test


def test_lines_from_order():
    at = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [{"id": 7, "status": "new", "created_at": at,
             "items": [{"sku": "kit-22", "quantity": 1, "price": 36860}, {"sku": "CAM-001", "quantity": 2, "price": 3600}]}]
    lines = order_lines(rows, at)
    assert [line[:2] for line in lines] == [[7, 0], [7, 1]]
    assert [(line[4], line[5], line[8]) for line in lines] == [("kit-22", True, 36860), ("CAM-001", False, 7200)]


@pytest.fixture
def ch():
    if not CH_URL:
        pytest.skip("CLICKHOUSE_TEST_URL не задан")
    import clickhouse_connect

    from ops.analytics import connect

    base, db = CH_URL.rsplit("/", 1)
    admin = clickhouse_connect.get_client(dsn=f"{base}/default")
    admin.command(f"drop database if exists {db}")
    admin.command(f"create database {db}")
    client = connect(CH_URL)
    yield client
    client.close()
    admin.close()


async def add_order(sessions, items, status="new", days_ago=1):
    async with sessions() as s:
        await s.execute(
            text("insert into public.site_orders (items, total, status, created_at) "
                 "values (cast(:items as jsonb), :total, :status, now() - make_interval(days => :days))"),
            {"items": json.dumps(items), "total": sum(i["quantity"] * i["price"] for i in items),
             "status": status, "days": days_ago},
        )
        await s.commit()


async def test_sync_is_idempotent_and_sees_status_changes(sessions, ch):
    await add_order(sessions, [{"sku": "kit-22", "quantity": 1, "price": 36860}])
    await add_order(sessions, [{"sku": "CAM-001", "quantity": 2, "price": 3600}])
    await add_order(sessions, [{"sku": "CAM-001", "quantity": 1, "price": 3600}], days_ago=90)  # вне окна

    async with sessions() as s:
        assert await sync_sales(s, ch, days=30) == {"orders": 2, "lines": 2}
        await sync_sales(s, ch, days=30)  # повтор — те же строки новой версии

    assert ch.query("select count() from sales_lines final").result_rows[0][0] == 2
    assert sum(r[2] for r in revenue_by_month(ch)) == 36860 + 7200

    async with sessions() as s:
        await s.execute(text("update public.site_orders set status = 'cancelled' where total = 7200"))
        await s.commit()
        await sync_sales(s, ch, days=30)

    assert sum(r[2] for r in revenue_by_month(ch)) == 36860  # отмена дошла до отчёта
    assert top_skus(ch)[0][0] == "kit-22"
