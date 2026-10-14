import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from ops.events import BadEvent, handle, parse, window_start
from ops.models import Job

BROKERS = os.environ.get("KAFKA_TEST_BROKERS", "localhost:9092")


def event(occurred: str, type_: str = "order.created", event_id: str | None = None) -> dict:
    return {"event_id": event_id or str(uuid.uuid4()), "type": type_, "occurred_at": occurred, "order_id": 1}


@pytest.mark.parametrize(
    "raw, reason",
    [
        (b"not json", "не JSON"),
        (b"[1]", "не объект"),
        (json.dumps({"type": "order.created", "occurred_at": "2026-10-14T10:00:00Z"}).encode(), "event_id"),
        (json.dumps(event("вчера")).encode(), "не дата"),
        (json.dumps(event("2026-10-14T10:00:00")).encode(), "часового пояса"),
    ],
)
def test_bad_events_are_rejected_with_reason(raw, reason):
    with pytest.raises(BadEvent, match=reason):
        parse(raw)


def test_window_is_ten_minutes_in_utc():
    moment = datetime.fromisoformat("2026-10-14T13:27:45+03:00")
    assert window_start(moment) == datetime(2026, 10, 14, 10, 20, tzinfo=UTC)


async def count_jobs(sessions) -> int:
    async with sessions() as s:
        return (await s.execute(select(func.count()).select_from(Job))).scalar_one()


async def test_orders_in_one_window_give_one_recalculation(sessions):
    async with sessions() as s:
        results = [
            await handle(s, parse(json.dumps(event(t)).encode()))
            for t in ("2026-10-14T10:01:00Z", "2026-10-14T10:09:59Z", "2026-10-14T10:10:00Z")
        ]
    assert results == ["queued", "coalesced", "queued"]
    assert await count_jobs(sessions) == 2


async def test_redelivery_does_not_duplicate(sessions):
    same = json.dumps(event("2026-10-14T10:05:00Z", event_id="e-1")).encode()
    async with sessions() as s:
        assert await handle(s, parse(same)) == "queued"
        assert await handle(s, parse(same)) == "coalesced"
    async with sessions() as s:
        job = (await s.execute(select(Job))).scalar_one()
    assert job.kind == "procurement" and job.run_after == datetime(2026, 10, 14, 10, 10, tzinfo=UTC)


async def test_foreign_event_types_are_ignored(sessions):
    async with sessions() as s:
        assert await handle(s, parse(json.dumps(event("2026-10-14T10:00:00Z", "order.paid")).encode())) == "ignored"
    assert await count_jobs(sessions) == 0


async def test_kafka_end_to_end(sessions):
    """Живой брокер: две записи одного окна, мусор в DLQ, смещения закоммичены."""
    aiokafka = pytest.importorskip("aiokafka")
    from ops import events

    topic_suffix = uuid.uuid4().hex[:8]
    events.TOPIC, events.DLQ_TOPIC, events.GROUP = (
        f"orders-{topic_suffix}",
        f"orders-{topic_suffix}.dlq",
        f"ops-{topic_suffix}",
    )
    producer = aiokafka.AIOKafkaProducer(bootstrap_servers=BROKERS)
    try:
        await asyncio.wait_for(producer.start(), 10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Kafka недоступна: {exc}")
    try:
        for payload in (
            json.dumps(event("2026-10-14T11:01:00Z")).encode(),
            json.dumps(event("2026-10-14T11:02:00Z")).encode(),
            b"{broken",
        ):
            await producer.send_and_wait(events.TOPIC, payload, key=b"42")
    finally:
        await producer.stop()

    async def run_until(expected_processed: int) -> None:
        stop = asyncio.Event()
        before = events.metrics.EVENTS._metrics.copy()
        task = asyncio.create_task(events.consume(sessions, BROKERS, stop))
        for _ in range(100):
            total = sum(c._value.get() for c in events.metrics.EVENTS._metrics.values())
            done = total - sum(c._value.get() for c in before.values())
            if done >= expected_processed:
                break
            await asyncio.sleep(0.2)
        stop.set()
        await asyncio.wait_for(task, 15)

    await run_until(3)
    assert await count_jobs(sessions) == 1

    dlq = aiokafka.AIOKafkaConsumer(events.DLQ_TOPIC, bootstrap_servers=BROKERS, auto_offset_reset="earliest")
    await dlq.start()
    try:
        msg = await asyncio.wait_for(dlq.getone(), 10)
        assert msg.value == b"{broken" and dict(msg.headers)["error"].startswith(b"\xd0")  # причина по-русски
    finally:
        await dlq.stop()

    # Смещение группы закоммичено за всеми тремя сообщениями: после рестарта повторной обработки не будет.
    from aiokafka.admin import AIOKafkaAdminClient

    admin = AIOKafkaAdminClient(bootstrap_servers=BROKERS)
    await admin.start()
    try:
        offsets = await admin.list_consumer_group_offsets(events.GROUP)
    finally:
        await admin.close()
    committed = [o.offset for tp, o in offsets.items() if tp.topic == events.TOPIC]
    assert sum(committed) == 3
