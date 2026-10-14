import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from ops import queue, worker
from ops.db import make_engine, make_sessionmaker
from ops.tasks import TASKS


async def scalar(sessions, sql):
    async with sessions() as s:
        return (await s.execute(text(sql))).scalar()


async def test_idempotency_key_returns_same_job(sessions):
    async with sessions() as s:
        a, created_a = await queue.enqueue(s, "noop", idempotency_key="k1")
        b, created_b = await queue.enqueue(s, "noop", idempotency_key="k1")
    assert created_a and not created_b and a.id == b.id
    assert await scalar(sessions, "select count(*) from ops.jobs") == 1
    async with sessions() as s:
        c, _ = await queue.enqueue(s, "noop", idempotency_key="k2")
    assert c.id == a.id + 1  # повторная постановка не съела номер


async def test_priority_then_age(sessions):
    async with sessions() as s:
        low, _ = await queue.enqueue(s, "noop", priority=0)
        high, _ = await queue.enqueue(s, "noop", priority=10)
        later, _ = await queue.enqueue(s, "noop", priority=0, run_after=datetime.now(timezone.utc) + timedelta(hours=1))
        order = [(await queue.claim(s, "w")).id, (await queue.claim(s, "w")).id]
        assert order == [high.id, low.id]
        assert await queue.claim(s, "w") is None  # отложенная ещё не готова
        assert later.id not in order


async def test_concurrent_workers_take_each_job_once(sessions, db_url, monkeypatch):
    """8 воркеров со своими соединениями разбирают 200 задач: ни одна не выполнена дважды."""
    seen: list[int] = []

    async def record(session, payload):
        seen.append(payload["n"])
        await asyncio.sleep(0.005)
        return {"n": payload["n"]}

    monkeypatch.setitem(TASKS, "record", record)
    async with sessions() as s:
        for n in range(200):
            await queue.enqueue(s, "record", {"n": n})

    async def run_worker(i: int) -> int:
        engine = make_engine(db_url)
        own = make_sessionmaker(engine)
        done = 0
        while await worker.run_one(own, f"w{i}"):
            done += 1
        await engine.dispose()
        return done

    per_worker = await asyncio.gather(*(run_worker(i) for i in range(8)))
    assert sum(per_worker) == 200
    assert sorted(seen) == list(range(200))
    assert sum(1 for d in per_worker if d > 0) > 1  # работа действительно распределилась
    assert await scalar(sessions, "select count(*) from ops.jobs where status='done'") == 200
    assert await scalar(sessions, "select count(*) from ops.job_runs") == 200


async def test_retry_with_backoff_then_success(sessions, monkeypatch):
    calls = 0

    async def flaky(session, payload):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("поставщик не ответил")
        return {"ok": True}

    monkeypatch.setitem(TASKS, "flaky", flaky)
    monkeypatch.setattr(queue, "backoff", lambda attempt: timedelta(0))
    async with sessions() as s:
        job, _ = await queue.enqueue(s, "flaky")
    while await worker.run_one(sessions, "w"):
        pass
    assert calls == 3
    async with sessions() as s:
        row = (await s.execute(text(f"select status, attempts from ops.jobs where id={job.id}"))).one()
        runs = (await s.execute(text(f"select ok from ops.job_runs where job_id={job.id} order by id"))).scalars().all()
    assert tuple(row) == ("done", 3)
    assert runs == [False, False, True]


async def test_backoff_delays_retry(sessions, monkeypatch):
    async def boom(session, payload):
        raise ValueError("сломано")

    monkeypatch.setitem(TASKS, "boom", boom)
    async with sessions() as s:
        await queue.enqueue(s, "boom")
    assert await worker.run_one(sessions, "w")
    assert not await worker.run_one(sessions, "w")  # повтор только через 10 секунд
    assert await scalar(sessions, "select status from ops.jobs") == "failed"
    assert await scalar(sessions, "select last_error from ops.jobs") == "ValueError: сломано"


async def test_dead_after_max_attempts(sessions, monkeypatch):
    async def boom(session, payload):
        raise ValueError("сломано")

    monkeypatch.setitem(TASKS, "boom", boom)
    monkeypatch.setattr(queue, "backoff", lambda attempt: timedelta(0))
    async with sessions() as s:
        await queue.enqueue(s, "boom", max_attempts=2)
    while await worker.run_one(sessions, "w"):
        pass
    assert await scalar(sessions, "select status || ':' || attempts from ops.jobs") == "dead:2"


async def test_unknown_kind_does_not_crash_worker(sessions):
    async with sessions() as s:
        await queue.enqueue(s, "no_such_task", max_attempts=1)
    assert await worker.run_one(sessions, "w")
    assert await scalar(sessions, "select status from ops.jobs") == "dead"


async def test_timeout_counts_as_failure(sessions, monkeypatch):
    async def slow(session, payload):
        await asyncio.sleep(5)

    monkeypatch.setitem(TASKS, "slow", slow)
    monkeypatch.setattr(worker, "JOB_TIMEOUT", 0.1)
    async with sessions() as s:
        await queue.enqueue(s, "slow")
    assert await worker.run_one(sessions, "w")
    assert (await scalar(sessions, "select last_error from ops.jobs")).startswith("TimeoutError")


async def test_housekeeping_reclaims_stale_and_expires(sessions):
    async with sessions() as s:
        stuck, _ = await queue.enqueue(s, "noop")
        late, _ = await queue.enqueue(s, "noop", deadline=datetime.now(timezone.utc) + timedelta(hours=1))
        await s.execute(text(f"update ops.jobs set status='running', attempts=1, locked_by='dead', locked_at=now() - interval '1 hour' where id={stuck.id}"))
        await s.execute(text(f"update ops.jobs set deadline = now() - interval '1 minute' where id={late.id}"))
        await s.commit()
        assert await queue.housekeeping(s) == {"stale": 1, "expired": 1}
        statuses = dict((await s.execute(text("select id, status from ops.jobs"))).all())
    assert statuses == {stuck.id: "failed", late.id: "expired"}


async def test_schedule_is_idempotent(sessions):
    msk_noon = datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    async with sessions() as s:
        assert await worker.schedule_daily(s, msk_noon) == 4
        assert await worker.schedule_daily(s, msk_noon) == 0
    early = datetime(2026, 10, 13, 4, 0, tzinfo=timezone(timedelta(hours=3)))
    async with sessions() as s:
        assert await worker.schedule_daily(s, early) == 1  # в 4 утра — только выгрузка


async def test_metrics_reflect_queue(sessions, monkeypatch):
    from ops import metrics

    async def boom(session, payload):
        raise ValueError("сломано")

    monkeypatch.setitem(TASKS, "boom", boom)
    async with sessions() as s:
        await queue.enqueue(s, "boom", max_attempts=1, priority=10)
        await queue.enqueue(s, "noop", run_after=datetime.now(timezone.utc) - timedelta(minutes=5))
    before = metrics.JOBS.labels("boom", "dead")._value.get()
    assert await worker.run_one(sessions, "w")  # boom → dead
    assert metrics.JOBS.labels("boom", "dead")._value.get() == before + 1
    async with sessions() as s:
        await metrics.collect_queue(s)
    assert metrics.QUEUE.labels("dead")._value.get() == 1
    assert metrics.QUEUE.labels("queued")._value.get() == 1
    assert metrics.OLDEST_READY._value.get() >= 299
    assert metrics.DEAD_RECENT.labels("boom")._value.get() == 1
