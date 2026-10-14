"""События заказов из Kafka → задачи очереди ops.

Витрина публикует `order.created` в топик `orders` (ключ — id заказа, поэтому события
одного заказа идут по порядку в одной партиции). Сервис читает их группой `ops` и ставит
пересчёт закупок.

Доставка «как минимум один раз»: смещение коммитится в Kafka только после того, как
задача записана в базу. Упали между ними — событие придёт ещё раз, и дубль отсекает
ключ идемпотентности задачи. Ключ строится из времени события, а не из времени получения:
повторная доставка попадает в то же окно, а все заказы одного окна дают один пересчёт.

Событие, которое нельзя разобрать, уходит в `orders.dlq` с причиной и не блокирует партицию.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ops import metrics
from ops.queue import enqueue

log = logging.getLogger("ops.events")

TOPIC = "orders"
DLQ_TOPIC = "orders.dlq"
GROUP = "ops"
WINDOW = timedelta(minutes=10)


class BadEvent(ValueError):
    """Событие не по схеме — в DLQ, повторять бесполезно."""


def parse(raw: bytes) -> dict[str, Any]:
    try:
        event = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadEvent(f"не JSON: {exc}") from exc
    if not isinstance(event, dict):
        raise BadEvent("событие не объект")
    for field in ("event_id", "type", "occurred_at"):
        if not event.get(field):
            raise BadEvent(f"нет поля {field}")
    try:
        event["occurred_at"] = datetime.fromisoformat(str(event["occurred_at"]))
    except ValueError as exc:
        raise BadEvent(f"occurred_at не дата: {exc}") from exc
    if event["occurred_at"].tzinfo is None:
        raise BadEvent("occurred_at без часового пояса")
    return event


def window_start(moment: datetime) -> datetime:
    moment = moment.astimezone(UTC)
    return moment - timedelta(minutes=moment.minute % 10, seconds=moment.second, microseconds=moment.microsecond)


async def handle(session: AsyncSession, event: dict[str, Any]) -> str:
    """Применяет разобранное событие. Возвращает результат для метрик и логов."""
    if event["type"] != "order.created":
        return "ignored"  # чужие типы в топике — не ошибка, их читают другие
    start = window_start(event["occurred_at"])
    _, created = await enqueue(
        session,
        "procurement",
        {"trigger": "order.created", "window": start.isoformat()},
        priority=5,
        run_after=start + WINDOW,  # пересчёт после окна: пачка заказов — одна задача
        idempotency_key=f"procurement:orders:{start:%Y%m%dT%H%M}",
    )
    return "queued" if created else "coalesced"


async def consume(sessions: async_sessionmaker, brokers: str, stop: asyncio.Event | None = None) -> None:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    consumer = AIOKafkaConsumer(
        TOPIC, bootstrap_servers=brokers, group_id=GROUP, enable_auto_commit=False, auto_offset_reset="earliest"
    )
    dlq = AIOKafkaProducer(bootstrap_servers=brokers)
    await consumer.start()
    await dlq.start()
    try:
        while stop is None or not stop.is_set():
            batch = await consumer.getmany(timeout_ms=500)
            for messages in batch.values():
                for msg in messages:
                    try:
                        event = parse(msg.value)
                        async with sessions() as session:
                            result = await handle(session, event)
                    except BadEvent as exc:
                        result = "dead_letter"
                        await dlq.send_and_wait(
                            DLQ_TOPIC, msg.value, key=msg.key, headers=[("error", str(exc).encode())]
                        )
                    metrics.EVENTS.labels(result).inc()
                    log.info("событие %s/%s: %s", msg.partition, msg.offset, result)
                    # Смещение — только после записи в базу (или в DLQ).
                    await consumer.commit()
    finally:
        await consumer.stop()
        await dlq.stop()


async def main() -> None:
    from ops import config
    from ops.db import make_engine, make_sessionmaker

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    engine = make_engine()
    try:
        await consume(make_sessionmaker(engine), config.KAFKA_BROKERS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
