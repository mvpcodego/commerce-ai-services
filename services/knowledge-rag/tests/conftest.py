"""Тесты с БД идут в отдельную схему rag_test той же локальной базы (docker compose up -d)
и пропускаются, если Postgres недоступен. Эмбеддер в тестах — HashEmbedder: без скачивания моделей."""

import os

import psycopg
import pytest

from rag.chunking import chunk_corpus
from rag.corpus import build_corpus
from rag.embed import HashEmbedder
from rag.store import Store

URL = os.environ.get("RAG_TEST_DATABASE_URL", "postgresql://rag:rag@127.0.0.1:5435/rag")


@pytest.fixture(scope="session")
def corpus():
    return build_corpus()


@pytest.fixture(scope="session")
def store(corpus):
    try:
        conn = psycopg.connect(URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен: docker compose up -d")
    conn.execute("drop schema if exists rag_test cascade")
    s = Store(conn, "rag_test")
    s._set_path()
    s.migrate()
    chunks = chunk_corpus(corpus)
    emb = HashEmbedder()
    s.load(corpus, chunks, emb.embed_documents([c.content for c in chunks]), emb.name)
    yield s
    conn.execute("drop schema if exists rag_test cascade")
    conn.close()
