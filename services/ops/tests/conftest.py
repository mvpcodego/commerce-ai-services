"""Тесты ходят в отдельный локальный Postgres, не в боевую базу:
docker run -d --name ops-test-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=ops_test -p 127.0.0.1:5434:5432 postgres:16
"""

import os

URL = os.environ.get("OPS_TEST_DATABASE_URL", "postgresql+psycopg://postgres:test@127.0.0.1:5434/ops_test")
# До импорта ops.config: тесты не должны видеть адрес боевой базы из .env (config берёт
# значение окружения раньше файла), а Celery без брокера работает в памяти.
os.environ["OPS_DATABASE_URL"] = URL
os.environ["CELERY_BROKER_URL"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from ops.db import make_engine, make_sessionmaker  # noqa: E402

HERE = os.path.dirname(__file__)

# Исходные таблицы в том виде, в каком их видит сервис (колонки — подмножество боевых).
SOURCE_DDL = """
drop schema if exists ops cascade;
drop table if exists public.site_orders, public.parts, public.kits;
drop type if exists public.part_type;
create schema ops;
-- Как в боевой базе: type — enum, а не text (на этом ломалось сравнение в фиде).
create type public.part_type as enum ('head_unit', 'frame', 'wiring', 'starter_kit', 'adapter',
  'camera', 'soundproofing', 'accessory', 'door_closer', 'audio', 'alarm', 'tuning');
create table public.parts (id bigint primary key, sku text unique, title text, type public.part_type,
  stock int not null default 0, price_retail int, archived boolean not null default false,
  brand text, image_url text);
create table public.kits (id bigint primary key, head_unit_id bigint, frame_id bigint,
  wiring_id bigint, starter_kit_id bigint);
create table public.site_orders (id bigint generated always as identity primary key,
  items jsonb not null default '[]', total int not null default 0,
  status text not null default 'new', created_at timestamptz not null default now());
"""


@pytest.fixture(scope="session")
def db_url() -> str:
    sync = create_engine(URL)
    try:
        with sync.begin() as c:
            c.execute(text(SOURCE_DDL))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"тестовая база недоступна: {exc}")
    finally:
        sync.dispose()
    cfg = Config(os.path.join(HERE, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "..", "migrations"))
    cfg.attributes["url"] = URL
    command.upgrade(cfg, "head")
    return URL


@pytest.fixture
async def sessions(db_url):
    engine = make_engine(db_url)
    async with engine.begin() as c:
        await c.execute(text("truncate ops.jobs, ops.job_runs, public.site_orders restart identity cascade"))
    yield make_sessionmaker(engine)
    await engine.dispose()
