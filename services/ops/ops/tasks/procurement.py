from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ops import procurement as calc
from ops.models import kits, parts, site_orders


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    # Те же границы, что у /api/procurement.
    try:
        return min(hi, max(lo, int(value)))
    except (TypeError, ValueError):
        return default


async def procurement(session: AsyncSession, payload: dict[str, Any]) -> dict[str, Any]:
    days = _clamp(payload.get("days"), 14, 365, 90)
    lead = _clamp(payload.get("lead"), 1, 120, 14)
    horizon = _clamp(payload.get("horizon"), 7, 180, 30)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    orders = (
        await session.execute(
            select(site_orders.c["items"], site_orders.c.status, site_orders.c.created_at).where(
                site_orders.c.created_at >= since
            )
        )
    ).mappings().all()
    part_rows = (await session.execute(select(parts))).mappings().all()
    kit_rows = (await session.execute(select(kits))).mappings().all()

    part_list = [dict(p) for p in part_rows]
    rows = calc.plan([dict(o) for o in orders], [dict(k) for k in kit_rows], part_list, days=days, lead=lead, horizon=horizon)
    return {
        "params": {"days": days, "lead": lead, "horizon": horizon},
        "orders": len(orders),
        "summary": calc.summarize(rows, part_list),
        # В результат кладём только то, что требует действия: полная таблица есть в дашборде.
        "reorder": [r for r in rows if r["reorder"] > 0],
    }
