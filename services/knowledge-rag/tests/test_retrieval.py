from rag.retrieval import Retriever, doc_ranking, rrf
from rag.store import Filters, Hit


def h(cid: str, doc: str | None = None) -> Hit:
    return Hit(cid, doc or cid.split("#")[0], "t", "x", 0.0)


def test_rrf_rewards_agreement():
    vec = [h("a#0"), h("b#0"), h("c#0")]
    fts = [h("b#0"), h("d#0")]
    fused = rrf([vec, fts], k=60)
    assert [x.chunk_id for x in fused] == ["b#0", "a#0", "d#0", "c#0"]
    assert abs(fused[0].score - (1 / 62 + 1 / 61)) < 1e-12


def test_rrf_ties_are_stable():
    assert [x.chunk_id for x in rrf([[h("b#0")], [h("a#0")]])] == ["a#0", "b#0"]


def test_doc_ranking_collapses_chunks():
    assert doc_ranking([h("a#1"), h("b#0"), h("a#0"), h("c#2")]) == ["a", "b", "c"]


class FakeBackend:
    def __init__(self):
        self.calls = []

    def vector_search(self, qvec, k, filters):
        self.calls.append(("vector", k, filters))
        return [h("a#0"), h("b#0")]

    def fulltext_search(self, question, k, filters):
        self.calls.append(("fulltext", k, filters))
        return [h("b#0"), h("c#0")]


class FakeEmbedder:
    name, dim = "fake", 2

    def embed_query(self, text):
        return [1.0, 0.0]

    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]


class ReverseReranker:
    name = "reverse"

    def scores(self, question, texts):
        return list(range(len(texts)))  # последний — лучший


def test_hybrid_passes_filters_to_both_lists():
    backend = FakeBackend()
    f = Filters(make="Kia")
    hits = Retriever(backend, FakeEmbedder(), candidates=7).search("q", "hybrid", 2, f)
    assert [x.chunk_id for x in hits] == ["b#0", "a#0"]
    assert backend.calls == [("vector", 7, f), ("fulltext", 7, f)]


def test_rerank_reorders_fused_top():
    r = Retriever(FakeBackend(), FakeEmbedder(), reranker=ReverseReranker())
    assert [x.chunk_id for x in r.search("q", "rerank", 3)] == ["c#0", "a#0", "b#0"]


def test_filters_sql_include_general_rows():
    where, args = Filters(make="Kia", model="Rio").where()
    assert args == ["Kia", "Rio"]
    assert "is null" in where.as_string(None)
    strict, _ = Filters(make="Kia", include_general=False).where()
    assert "is null" not in strict.as_string(None)


class RecordingBackend(FakeBackend):
    def fulltext_search(self, question, k, filters):
        self.question = question
        return []


def test_filter_car_is_added_to_query_text():
    backend = RecordingBackend()
    Retriever(backend, FakeEmbedder()).search("какая рамка?", "hybrid", 3, Filters(make="Haval", model="Jolion"))
    assert backend.question == "какая рамка? Haval Jolion"
