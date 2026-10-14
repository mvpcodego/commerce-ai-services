from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ops import config
from ops.analytics import connect, sync_sales


async def analytics_sync(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.CLICKHOUSE_URL:
        return {"skipped": "CLICKHOUSE_URL не задан"}
    client = connect()
    try:
        return await sync_sales(session, client, days=int(payload.get("days", 30)))
    finally:
        client.close()
