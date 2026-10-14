"""Celery поверх RabbitMQ для тяжёлых задач, которые выгодно распараллелить.

Очередь на Postgres (ops.queue) остаётся главной: она ставит задачи по расписанию,
хранит историю и шлёт тревоги. Celery получает от неё работу, которую имеет смысл
разложить на части и выполнить параллельно, — сейчас это фид для Яндекс.Маркета.
Запуск воркера: celery -A ops.celery_app worker --concurrency=2
"""

from celery import Celery

from ops import config

# Результаты — в той же базе, в схеме ops (таблицы celery_taskmeta/celery_tasksetmeta создаёт
# сам Celery): chord-у нужно хранилище, которое видят все воркеры, а «rpc» его не поддерживает.
# Плюс история задач Celery лежит рядом с историей очереди на Postgres.
backend = "db+" + config.DATABASE_URL if config.DATABASE_URL else "cache+memory://"
app = Celery("ops", broker=config.CELERY_BROKER_URL or "memory://", backend=backend, include=["ops.feed"])
app.conf.update(
    database_table_schemas={"task": "ops", "group": "ops"},
    database_engine_options={"pool_pre_ping": True, "pool_size": 2},
    result_expires=7 * 24 * 3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    # Подтверждение после выполнения: упавший посреди задачи воркер не теряет её,
    # RabbitMQ отдаст сообщение другому.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
    broker_connection_retry_on_startup=True,
)
