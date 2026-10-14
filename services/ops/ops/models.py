"""Таблицы сервиса (схема ops, ими владеет Alembic) и исходные таблицы (public, только чтение)."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(schema="ops")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Больше — раньше. Ручной запуск из дашборда идёт выше ночных задач.
    priority: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    # queued → running → done | failed (ждёт повтора) | dead (попытки кончились) | expired
    status: Mapped[str] = mapped_column(Text, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, server_default="5")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Задача, не начатая до срока, теряет смысл: сводка за вчера к вечеру никому не нужна.
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Один ключ — одна задача: повторная постановка возвращает уже существующую.
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobRun(Base):
    """Журнал попыток: по нему видно, сколько раз задача падала и почему."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("ops.jobs.id", ondelete="cascade"))
    attempt: Mapped[int] = mapped_column(Integer)
    worker: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)


# Исходные таблицы приложения. Описаны только нужные колонки — у роли сервиса
# права есть только на них (данные покупателей ей закрыты, миграция 0008); схемой public
# владеют миграции Supabase, Alembic их не трогает (см. migrations/env.py).
source = MetaData(schema="public")

site_orders = Table(
    "site_orders",
    source,
    Column("id", BigInteger, primary_key=True),
    Column("items", JSONB),
    Column("total", Integer),
    Column("status", Text),
    Column("created_at", DateTime(timezone=True)),
)

parts = Table(
    "parts",
    source,
    Column("id", BigInteger, primary_key=True),
    Column("sku", Text),
    Column("title", Text),
    Column("type", Text),
    Column("stock", Integer),
    Column("price_retail", Integer),
    Column("archived", Boolean),
    Column("brand", Text),
    Column("image_url", Text),
)

kits = Table(
    "kits",
    source,
    Column("id", BigInteger, primary_key=True),
    Column("head_unit_id", BigInteger),
    Column("frame_id", BigInteger),
    Column("wiring_id", BigInteger),
    Column("starter_kit_id", BigInteger),
)
