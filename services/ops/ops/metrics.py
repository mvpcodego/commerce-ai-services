"""Метрики для Prometheus: очередь, задачи, база и доступность сайтов.

Воркер отдаёт их на :9108/metrics внутри сети docker, наружу порт не публикуется.
"""

import time

import httpx
from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

PORT = 9108
SITES = {"shop": "https://tmgoods.ru/shop", "dashboard": "https://demo.mvp-code.ru/login"}

JOBS = Counter("ops_jobs_total", "Выполненные попытки задач", ["kind", "result"])
JOB_SECONDS = Histogram(
    "ops_job_duration_seconds", "Длительность задачи", ["kind"], buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 300)
)
QUEUE = Gauge("ops_queue_jobs", "Задачи в очереди по статусу", ["status"])
DEAD_RECENT = Gauge(
    "ops_queue_dead_last_hour", "Задачи, исчерпавшие попытки за последний час", ["kind"]
)
OLDEST_READY = Gauge("ops_queue_oldest_ready_seconds", "Сколько ждёт самая старая готовая к запуску задача")
DB_SECONDS = Gauge("ops_db_roundtrip_seconds", "Время запроса select 1 до базы")
SITE_UP = Gauge("ops_site_up", "Сайт ответил 200", ["site"])
SITE_SECONDS = Gauge("ops_site_response_seconds", "Время ответа сайта", ["site"])
EVENTS = Counter("ops_events_total", "События из Kafka по результату", ["result"])
LAST_TICK = Gauge("ops_worker_last_tick_timestamp", "Последний служебный цикл воркера")

STATUSES = ("queued", "running", "done", "failed", "dead", "expired")


async def collect_queue(session: AsyncSession) -> None:
    t = time.perf_counter()
    await session.execute(text("select 1"))
    DB_SECONDS.set(time.perf_counter() - t)

    counts = dict((await session.execute(text("select status, count(*) from ops.jobs group by status"))).all())
    for status in STATUSES:
        QUEUE.labels(status).set(counts.get(status, 0))
    oldest = (
        await session.execute(
            text(
                "select coalesce(extract(epoch from now() - min(run_after)), 0) from ops.jobs"
                " where status in ('queued','failed') and run_after <= now()"
            )
        )
    ).scalar_one()
    OLDEST_READY.set(float(oldest))

    # Отдельный показатель вместо increase() по счётчику: у ряда, который появился
    # сразу со значением 1, Prometheus не видит прироста, и оповещение молчало бы.
    dead = dict(
        (await session.execute(
            text("select kind, count(*) from ops.jobs where status='dead' and finished_at > now() - interval '1 hour' group by kind")
        )).all()
    )
    DEAD_RECENT.clear()
    for kind, n in dead.items():
        DEAD_RECENT.labels(kind).set(n)
    LAST_TICK.set_to_current_time()


async def probe_sites(client: httpx.AsyncClient) -> None:
    for name, url in SITES.items():
        t = time.perf_counter()
        try:
            r = await client.get(url)
            up = r.status_code == 200
        except httpx.HTTPError:
            up = False
        SITE_UP.labels(name).set(1 if up else 0)
        SITE_SECONDS.labels(name).set(time.perf_counter() - t)
