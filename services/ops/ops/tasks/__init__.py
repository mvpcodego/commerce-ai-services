"""Реестр задач: kind → корутина (session, payload) → result."""

from ops.tasks.analytics_sync import analytics_sync
from ops.tasks.daily_summary import daily_summary
from ops.tasks.export_orders import export_orders
from ops.tasks.market_feed import market_feed
from ops.tasks.procurement import procurement

TASKS = {
    "procurement": procurement,
    "export_orders": export_orders,
    "daily_summary": daily_summary,
    "market_feed": market_feed,
    "analytics_sync": analytics_sync,
}
