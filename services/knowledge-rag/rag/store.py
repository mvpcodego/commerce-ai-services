"""Хранилище в PostgreSQL + pgvector: миграции, загрузка, вектор и полнотекст с фильтрами."""

import os
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

from rag.chunking import Chunk
from rag.corpus import Doc

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
DEFAULT_URL = "postgresql://rag:rag@127.0.0.1:5435/rag"


def database_url() -> str:
    return os.environ.get("RAG_DATABASE_URL", DEFAULT_URL)


@dataclass(frozen=True)
class Filters:
    make: str | None = None
    model: str | None = None
    doc_type: str | None = None
    include_general: bool = True  # документы без марки (FAQ, магнитолы, наборы) проходят фильтр по марке

    def where(self, alias: str = "c") -> tuple[sql.Composable, list]:
        parts: list[sql.Composable] = []
        args: list = []
        for col, val in (("make", self.make), ("model", self.model)):
            if val:
                ident = sql.Identifier(alias, col)
                cond = sql.SQL("lower({}) = lower(%s)").format(ident)
                if self.include_general:
                    cond = sql.SQL("({} or {} is null)").format(cond, ident)
                parts.append(cond)
                args.append(val)
        if self.doc_type:
            parts.append(sql.SQL("{} = %s").format(sql.Identifier(alias, "doc_type")))
            args.append(self.doc_type)
        if not parts:
            return sql.SQL("true"), []
        return sql.SQL(" and ").join(parts), args


NO_FILTERS = Filters()


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    doc_id: str
    title: str
    text: str
    score: float


# Вопрос → tsquery через OR. websearch_to_tsquery соединяет слова через AND, и вопрос из восьми слов
# почти никогда не находит чанк целиком. Разбор слов делает сам Postgres (тот же парсер, что у tsvector:
# «10.1», «wi-fi», артикулы), Python только меняет AND на OR. Стоп-слова Postgres выбрасывает сам.
OR_TSQUERY = "replace(plainto_tsquery('russian', %s)::text, ' & ', ' | ')::tsquery"


class Store:
    def __init__(self, conn: psycopg.Connection, schema: str = "public") -> None:
        self.conn = conn
        self.schema = schema

    @classmethod
    def connect(cls, url: str | None = None, schema: str = "public") -> "Store":
        conn = psycopg.connect(url or database_url(), autocommit=True)
        store = cls(conn, schema)
        store._set_path()
        return store

    def _set_path(self) -> None:
        self.conn.execute(sql.SQL("create schema if not exists {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL("set search_path to {}, public").format(sql.Identifier(self.schema)))

    def migrate(self) -> list[str]:
        self.conn.execute(
            "create table if not exists schema_migrations (name text primary key, applied_at timestamptz default now())"
        )
        done = {r[0] for r in self.conn.execute("select name from schema_migrations")}
        applied = []
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            with self.conn.transaction():
                self.conn.execute(f.read_text("utf-8"))
                self.conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            applied.append(f.name)
        register_vector(self.conn)
        # Фильтр по метаданным после HNSW может оставить меньше k строк — итеративный обход (pgvector ≥ 0.8) добирает.
        self.conn.execute("set hnsw.iterative_scan = relaxed_order")
        self.conn.execute("set hnsw.ef_search = 100")
        return applied

    def load(self, docs: list[Doc], chunks: list[Chunk], vectors: list[list[float]], embedder: str) -> None:
        """Полная перезаливка в одной транзакции: корпус генерируется целиком, частичных обновлений нет."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("truncate documents cascade")
            cur.executemany(
                "insert into documents (doc_id, doc_type, title, body, make, model) values (%s,%s,%s,%s,%s,%s)",
                [(d.doc_id, d.doc_type, d.title, d.text, d.make, d.model) for d in docs],
            )
            cur.executemany(
                "insert into chunks (chunk_id, doc_id, ord, title, content, text, doc_type, make, model, embedding)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                [
                    (c.chunk_id, c.doc_id, c.ord, c.title, c.content, c.text, c.doc_type, c.make, c.model, str(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
            cur.execute(
                "insert into kb_meta values ('embedder', %s) on conflict (key) do update set value = excluded.value",
                (embedder,),
            )

    def embedder_name(self) -> str | None:
        row = self.conn.execute("select value from kb_meta where key = 'embedder'").fetchone()
        return row[0] if row else None

    def count(self) -> tuple[int, int]:
        row = self.conn.execute("select (select count(*) from documents), (select count(*) from chunks)").fetchone()
        return row[0], row[1]

    def vector_search(self, qvec: list[float], k: int = 20, filters: Filters = NO_FILTERS) -> list[Hit]:
        where, args = filters.where("c")
        q = sql.SQL(
            "select c.chunk_id, c.doc_id, d.title, c.text, 1 - (c.embedding <=> %s::vector) as score"
            " from chunks c join documents d on d.doc_id = c.doc_id"
            " where {} order by c.embedding <=> %s::vector limit %s"
        ).format(where)
        vec = str(qvec)
        return [Hit(*r) for r in self.conn.execute(q, [vec, *args, vec, k])]

    def fulltext_search(self, question: str, k: int = 20, filters: Filters = NO_FILTERS) -> list[Hit]:
        if not question.strip():
            return []
        where, args = filters.where("c")
        q = sql.SQL(
            "select c.chunk_id, c.doc_id, d.title, c.text, ts_rank_cd(c.tsv, t.q, 1) as score"
            " from chunks c join documents d on d.doc_id = c.doc_id,"
            " (select " + OR_TSQUERY + " as q) t where c.tsv @@ t.q and {} order by score desc, c.chunk_id limit %s"
        ).format(where)
        return [Hit(*r) for r in self.conn.execute(q, [question, *args, k])]
