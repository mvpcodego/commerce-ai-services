from datetime import date
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ops import config
from ops.models import site_orders
from ops.tasks.export_orders import day_bounds, yesterday


def _rub(n: int) -> str:
    return f"{n:,}".replace(",", " ") + " ₽"


async def daily_summary(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    day = date.fromisoformat(payload["day"]) if payload.get("day") else yesterday()
    start, end = day_bounds(day)
    rows = (
        await session.execute(
            select(site_orders.c.status, func.count(), func.coalesce(func.sum(site_orders.c.total), 0))
            .where(site_orders.c.created_at >= start, site_orders.c.created_at < end)
            .group_by(site_orders.c.status)
        )
    ).all()
    by_status = {status: (count, total) for status, count, total in rows}
    cancelled = by_status.pop("cancelled", (0, 0))
    orders = sum(c for c, _ in by_status.values())
    revenue = sum(t for _, t in by_status.values())

    lines = [f"Продажи за {day.strftime('%d.%m.%Y')}", f"Заказов: {orders}", f"Сумма: {_rub(revenue)}"]
    if orders:
        lines.append(f"Средний чек: {_rub(revenue // orders)}")
    if cancelled[0]:
        lines.append(f"Отменено: {cancelled[0]} на {_rub(cancelled[1])}")
    text = "\n".join(lines)

    sent = False
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            )
            # Ошибка Telegram роняет задачу — очередь повторит её с паузой. Текст ошибки
            # httpx содержит адрес с токеном бота, поэтому в журнал идёт только код.
            if r.is_error:
                raise RuntimeError(f"Telegram ответил {r.status_code}")
            sent = True
    return {"day": day.isoformat(), "orders": orders, "revenue": revenue, "cancelled": cancelled[0], "sent": sent, "text": text}
