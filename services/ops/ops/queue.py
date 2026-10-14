"""Очередь задач на Postgres.

Отдельный брокер не нужен: задач десятки в день, а база уже есть. Захват идёт
через FOR UPDATE SKIP LOCKED — несколько воркеров берут разные задачи и не ждут
друг друга. Задача, которая упала, возвращается в очередь с растущей паузой;
кончились попытки — dead. Воркер, умерший посреди задачи, держит её не дольше
STALE_AFTER: потом она снова доступна.
"""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ops.models import Job, JobRun

STALE_AFTER = timedelta(minutes=10)


def backoff(attempt: int) -> timedelta:
    """10 с, 20 с, 40 с … но не больше 10 минут."""
    return timedelta(seconds=min(10 * 2 ** (attempt - 1), 600))


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 0,
    run_after: datetime | None = None,
    deadline: datetime | None = None,
    idempotency_key: str | None = None,
    max_attempts: int = 5,
) -> tuple[Job, bool]:
    """Ставит задачу. Возвращает (задача, создана ли новая)."""
    if idempotency_key is not None:
        # Сначала проверка, потом вставка: insert … on conflict тратит номер из
        # последовательности даже при конфликте, а планировщик повторяет постановку
        # каждую минуту — номера задач шли бы с пропусками в тысячи.
        found = (await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))).scalar_one_or_none()
        if found is not None:
            return found, False
    values: dict[str, Any] = {
        "kind": kind,
        "payload": payload or {},
        "priority": priority,
        "deadline": deadline,
        "idempotency_key": idempotency_key,
        "max_attempts": max_attempts,
    }
    if run_after is not None:
        values["run_after"] = run_after
    stmt = insert(Job).values(**values).on_conflict_do_nothing(index_elements=["idempotency_key"]).returning(Job)
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is not None:
        await session.commit()
        return job, True
    existing = (await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))).scalar_one()
    return existing, False


_CLAIM = text(
    """
    update ops.jobs j
       set status = 'running', attempts = j.attempts + 1, locked_by = :worker, locked_at = now()
     where j.id = (
           select id from ops.jobs
            where status in ('queued', 'failed')
              and run_after <= now()
              and (deadline is null or deadline > now())
            order by priority desc, run_after, id
            for update skip locked
            limit 1)
    returning j.id
    """
)


async def claim(session: AsyncSession, worker: str) -> Job | None:
    """Берёт одну готовую задачу или None. Транзакция короткая: держим строку только на время update."""
    job_id = (await session.execute(_CLAIM, {"worker": worker})).scalar_one_or_none()
    await session.commit()
    if job_id is None:
        return None
    return await session.get(Job, job_id, populate_existing=True)


async def _log_run(session: AsyncSession, job: Job, ok: bool, error: str | None) -> None:
    started = job.locked_at
    now = (await session.execute(text("select now()"))).scalar_one()
    session.add(
        JobRun(
            job_id=job.id,
            attempt=job.attempts,
            worker=job.locked_by or "",
            started_at=started,
            ok=ok,
            error=error,
            duration_ms=int((now - started).total_seconds() * 1000) if started else 0,
        )
    )


async def complete(session: AsyncSession, job: Job, result: dict[str, Any] | None) -> None:
    await _log_run(session, job, True, None)
    await session.execute(
        text(
            "update ops.jobs set status='done', result=cast(:result as jsonb), finished_at=now(),"
            " locked_by=null, locked_at=null, last_error=null where id=:id"
        ),
        {"id": job.id, "result": _json(result)},
    )
    await session.commit()


async def fail(session: AsyncSession, job: Job, error: str) -> str:
    """Отмечает неудачу. Возвращает новый статус: failed (будет повтор) или dead."""
    await _log_run(session, job, False, error)
    status = "dead" if job.attempts >= job.max_attempts else "failed"
    await session.execute(
        text(
            "update ops.jobs set status=:status, last_error=:error, locked_by=null, locked_at=null,"
            " run_after = now() + make_interval(secs => :delay),"
            " finished_at = case when :status = 'dead' then now() end"
            " where id=:id"
        ),
        {"id": job.id, "status": status, "error": error[:4000], "delay": backoff(job.attempts).total_seconds()},
    )
    await session.commit()
    return status


async def housekeeping(session: AsyncSession) -> dict[str, int]:
    """Возвращает в очередь задачи умерших воркеров и закрывает просроченные."""
    stale = await session.execute(
        text(
            "update ops.jobs set status = case when attempts >= max_attempts then 'dead' else 'failed' end,"
            " last_error = 'воркер не ответил за отведённое время', locked_by=null, locked_at=null"
            " where status='running' and locked_at < now() - make_interval(secs => :secs)"
        ),
        {"secs": STALE_AFTER.total_seconds()},
    )
    expired = await session.execute(
        text(
            "update ops.jobs set status='expired', finished_at=now()"
            " where status in ('queued','failed') and deadline is not null and deadline <= now()"
        )
    )
    await session.commit()
    return {"stale": stale.rowcount, "expired": expired.rowcount}


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)
