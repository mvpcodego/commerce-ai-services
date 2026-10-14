import csv
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ops import config
from ops.models import site_orders

MSK = ZoneInfo("Europe/Moscow")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Сутки по Москве в UTC: магазин живёт по московскому времени."""
    start = datetime.combine(day, time.min, MSK)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def yesterday() -> date:
    return datetime.now(MSK).date() - timedelta(days=1)


async def export_orders(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    day = date.fromisoformat(payload["day"]) if payload.get("day") else yesterday()
    start, end = day_bounds(day)
    rows = (
        await session.execute(
            select(site_orders)
            .where(site_orders.c.created_at >= start, site_orders.c.created_at < end)
            .order_by(site_orders.c.id)
        )
    ).mappings().all()

    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.EXPORT_DIR / f"orders-{day.isoformat()}.csv"
    tmp = path.with_suffix(".tmp")
    # Пишем во временный файл и переименовываем: повтор задачи не оставит половину файла.
    with tmp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "создан (МСК)", "статус", "сумма", "позиций", "состав"])
        for r in rows:
            items = r["items"] or []
            w.writerow(
                [
                    r["id"],
                    r["created_at"].astimezone(MSK).strftime("%Y-%m-%d %H:%M"),
                    r["status"],
                    r["total"],
                    sum(i.get("quantity", 0) for i in items),
                    ", ".join(f'{i.get("sku")}×{i.get("quantity")}' for i in items),
                ]
            )
    tmp.replace(path)
    return {"day": day.isoformat(), "orders": len(rows), "file": str(path)}
