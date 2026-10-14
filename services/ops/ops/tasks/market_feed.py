import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ops import config


async def market_feed(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    """Запускает сборку фида в Celery и ждёт результат.

    Задача очереди на Postgres остаётся «владельцем» работы: если Celery упадёт или не
    ответит за 4 минуты, она уйдёт на повтор, а после последней попытки — в dead и в Telegram.
    """
    from ops.feed import start_feed

    result = start_feed(str(config.EXPORT_DIR / "feed"))
    return await asyncio.to_thread(result.get, timeout=240, propagate=True)
