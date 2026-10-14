"""Воркер: забирает задачи из очереди и выполняет их. Запуск: python -m ops.worker

Несколько воркеров можно запускать параллельно — захват через SKIP LOCKED
не даст двум взять одну задачу. Плановые задачи ставит любой из них: ключ
идемпотентности не даст поставить одну и ту же дважды.
"""

import asyncio
import logging
import os
import socket
from time import perf_counter
from datetime import datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import httpx
from prometheus_client import start_http_server

from ops import metrics, queue
from ops.db import make_engine, make_sessionmaker
from ops.tasks import TASKS
from ops.tasks.export_orders import MSK, day_bounds

log = logging.getLogger("ops.worker")
JOB_TIMEOUT = 300

# (задача, час по Москве, приоритет). Срок — конец суток: вчерашняя сводка завтра не нужна.
SCHEDULE = [("export_orders", 3, 0), ("daily_summary", 9, 5), ("procurement", 6, 0), ("market_feed", 5, 0)]


async def schedule_daily(session: AsyncSession, now: datetime | None = None) -> int:
    now = (now or datetime.now(MSK)).astimezone(MSK)
    created = 0
    for kind, hour, priority in SCHEDULE:
        if now.time() < time(hour):
            continue
        day = now.date() - timedelta(days=1)
        _, end_of_today = day_bounds(now.date())
        _, new = await queue.enqueue(
            session,
            kind,
            {"day": day.isoformat()},
            priority=priority,
            deadline=end_of_today,
            idempotency_key=f"{kind}:{now.date().isoformat()}",
        )
        created += new
    return created


async def run_one(sessions: async_sessionmaker, worker: str) -> bool:
    """Выполняет одну задачу. False — очередь пуста."""
    async with sessions() as session:
        job = await queue.claim(session, worker)
        if job is None:
            return False
        handler = TASKS.get(job.kind)
        started = perf_counter()
        try:
            if handler is None:
                raise LookupError(f"неизвестная задача {job.kind!r}")
            # Задача работает в своей сессии: её ошибка не должна сломать запись о результате.
            async with sessions() as task_session:
                result = await asyncio.wait_for(handler(task_session, job.payload), JOB_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 — любая ошибка задачи идёт в журнал и на повтор
            status = await queue.fail(session, job, f"{type(exc).__name__}: {exc}")
            metrics.JOBS.labels(job.kind, status).inc()
            log.warning("задача %s #%s: %s (%s)", job.kind, job.id, status, exc)
        else:
            await queue.complete(session, job, result)
            metrics.JOBS.labels(job.kind, "done").inc()
            log.info("задача %s #%s выполнена", job.kind, job.id)
        finally:
            metrics.JOB_SECONDS.labels(job.kind).observe(perf_counter() - started)
        return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = f"{socket.gethostname()}:{os.getpid()}"
    engine = make_engine()
    sessions = make_sessionmaker(engine)
    start_http_server(metrics.PORT)
    probe = httpx.AsyncClient(timeout=15, follow_redirects=True)
    last_tick = datetime.min
    try:
        while True:
            if datetime.now() - last_tick > timedelta(minutes=1):
                # Служебный цикл не должен ронять воркер: сбой сети или базы — повод
                # для метрики и записи в журнал, а не для перезапуска контейнера.
                try:
                    async with sessions() as s:
                        await schedule_daily(s)
                        await queue.housekeeping(s)
                        await metrics.collect_queue(s)
                    await metrics.probe_sites(probe)
                except Exception:  # noqa: BLE001
                    log.exception("служебный цикл")
                last_tick = datetime.now()
            if not await run_one(sessions, worker):
                await asyncio.sleep(5)
    finally:
        await probe.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
