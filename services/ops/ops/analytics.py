"""Аналитика продаж в ClickHouse: строки заказов из Postgres → колоночная таблица.

Postgres хранит заказ целиком (items в jsonb) и отвечает за запись. Отчёты по месяцам,
позициям и статусам на годах истории — работа для колоночной базы: она читает только
нужные колонки и сжимает их. Сюда переливаются строки заказов, отчёты считаются здесь.

Повторная выгрузка безопасна: ReplacingMergeTree с ключом (order_id, line_no) и версией
synced_at оставляет последнюю версию строки. Поэтому выгрузка просто берёт окно последних
дней целиком — смена статуса заказа доходит до отчётов при следующем прогоне.
Слияние версий фоновое, отчёты читают с FINAL, чтобы не видеть ещё не схлопнутые дубли.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ops import config
from ops.models import site_orders

COLUMNS = ["order_id", "line_no", "created_at", "status", "sku", "is_kit", "quantity", "price", "amount", "synced_at"]

DDL = """
create table if not exists sales_lines (
    order_id   UInt64,
    line_no    UInt16,
    created_at DateTime('Europe/Moscow'),
    status     LowCardinality(String),
    sku        String,
    is_kit     Bool,
    quantity   UInt32,
    price      UInt32,
    amount     UInt64,
    synced_at  DateTime64(3, 'UTC')
)
engine = ReplacingMergeTree(synced_at)
partition by toYYYYMM(created_at)
order by (order_id, line_no)
"""


def connect(url: str | None = None) -> Client:
    """CLICKHOUSE_URL: http://user:password@host:8123/database"""
    client = clickhouse_connect.get_client(dsn=url or config.CLICKHOUSE_URL)
    client.command(DDL)
    return client


def order_lines(rows: list[dict[str, Any]], synced_at: datetime) -> list[list[Any]]:
    lines = []
    for row in rows:
        for no, item in enumerate(row["items"] or []):
            quantity, price = int(item.get("quantity") or 0), int(item.get("price") or 0)
            sku = str(item.get("sku", ""))
            lines.append([
                row["id"], no, row["created_at"], row["status"], sku, sku.startswith("kit-"),
                quantity, price, quantity * price, synced_at,
            ])
    return lines


async def sync_sales(session: AsyncSession, client: Client, days: int = 30) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (await session.execute(
        select(site_orders.c.id, site_orders.c["items"], site_orders.c.status, site_orders.c.created_at)
        .where(site_orders.c.created_at >= since)
    )).mappings().all()
    lines = order_lines([dict(r) for r in rows], datetime.now(UTC))
    if lines:
        client.insert("sales_lines", lines, column_names=COLUMNS)
    return {"orders": len(rows), "lines": len(lines)}


def revenue_by_month(client: Client) -> list[tuple]:
    return client.query(
        """
        select toStartOfMonth(created_at) as month, uniqExact(order_id) as orders, sum(amount) as revenue
        from sales_lines final
        where status != 'cancelled'
        group by month order by month
        """
    ).result_rows


def top_skus(client: Client, limit: int = 10) -> list[tuple]:
    return client.query(
        """
        select sku, sum(quantity) as units, sum(amount) as revenue
        from sales_lines final
        where status != 'cancelled'
        group by sku order by revenue desc limit {limit:UInt32}
        """,
        parameters={"limit": limit},
    ).result_rows
