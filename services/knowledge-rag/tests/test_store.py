from rag.embed import HashEmbedder
from rag.retrieval import Retriever
from rag.store import Filters


def test_load_counts_and_indexes(store, corpus):
    docs, chunks = store.count()
    assert docs == len(corpus) and chunks >= docs
    idx = {r[0] for r in store.conn.execute("select indexname from pg_indexes where schemaname = 'rag_test'")}
    assert {"chunks_embedding_hnsw", "chunks_tsv_gin"} <= idx
    assert store.embedder_name() == HashEmbedder.name


def test_migrate_is_idempotent(store):
    assert store.migrate() == []


def test_fulltext_handles_russian_morphology(store):
    hits = store.fulltext_search("гарантию на магнитолы", 5)
    assert hits[0].doc_id == "faq-warranty"


def test_make_filter_strict_and_general(store):
    r = Retriever(store, HashEmbedder())
    strict = r.search("рамка проводка", "hybrid", 20, Filters(make="kia", include_general=False))
    assert strict and {h.doc_id for h in strict} <= {"car-kia-rio", "car-kia-sportage", "car-kia-ceed"}
    general = r.search("доставка и возврат", "hybrid", 20, Filters(make="Kia", model="Rio"))
    ids = {h.doc_id for h in general}
    assert "faq-delivery" in ids
    assert not any(i.startswith("car-") and i != "car-kia-rio" for i in ids)


def test_vector_filter_returns_k_rows_after_hnsw(store):
    hits = store.vector_search(HashEmbedder().embed_query("магнитола"), 3, Filters(make="Lada", include_general=False))
    assert len(hits) == 3 and all(h.doc_id.startswith("car-lada") for h in hits)
