"""Alembic владеет только схемой ops. Схемой public управляют миграции Supabase
(supabase/migrations), и у роли сервиса там нет прав на изменение."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from ops import config as ops_config
from ops.models import Base

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    schema = getattr(obj, "schema", None) or getattr(getattr(obj, "table", None), "schema", None)
    return type_ != "table" or schema == "ops"


def do_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema="ops",
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    url = context.config.attributes.get("url") or ops_config.DATABASE_URL
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(do_run)
    await engine.dispose()


asyncio.run(run_online())
