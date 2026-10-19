"""Корпус → чанки → эмбеддинги → Postgres. uv run python -m rag.load [--embedder hash]"""

import argparse
import time

from rag.chunking import chunk_corpus
from rag.corpus import build_corpus
from rag.embed import make_embedder
from rag.store import Store


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default=None, help="e5 (по умолчанию) или hash")
    ap.add_argument("--max-chars", type=int, default=500)
    ap.add_argument("--overlap", type=int, default=1)
    args = ap.parse_args()

    store = Store.connect()
    print("миграции:", store.migrate() or "актуальны")
    docs = build_corpus()
    chunks = chunk_corpus(docs, args.max_chars, args.overlap)
    emb = make_embedder(args.embedder)
    t = time.perf_counter()
    vectors = emb.embed_documents([c.content for c in chunks])
    print(f"эмбеддинги {emb.name}: {len(chunks)} чанков за {time.perf_counter() - t:.1f} с")
    store.load(docs, chunks, vectors, emb.name)
    print("в базе документов/чанков:", store.count())


if __name__ == "__main__":
    main()
