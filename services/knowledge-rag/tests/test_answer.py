from fastapi.testclient import TestClient

from rag.answer import NO_ANSWER, ExtractiveLLM, answer_question, approx_tokens, build_context, check_citations
from rag.api import create_app
from rag.retrieval import Retriever
from rag.store import Hit

HITS = [
    Hit("faq-delivery#0", "faq-delivery", "Доставка", "В регионы отправляем СДЭК. Срок 2–7 рабочих дней.", 0.9),
    Hit("faq-returns#0", "faq-returns", "Возврат", "Вернуть товар можно в течение 14 дней.", 0.8),
]


class FakeLLM:
    """Отдаёт заготовленный текст — проверяем обвязку, а не модель."""

    name = "fake"

    def __init__(self, text: str):
        self.text = text
        self.seen = None

    def complete(self, system, question, context):
        self.seen = (system, question, context.render())
        return self.text


def test_context_budget_skips_what_does_not_fit():
    big = Hit("big#0", "big", "Большой", "слово " * 400, 1.0)
    ctx = build_context([big, *HITS], budget_tokens=100)
    assert [h.doc_id for h in ctx.hits] == ["faq-delivery", "faq-returns"]
    assert ctx.dropped == 1 and ctx.tokens <= 100
    assert approx_tokens("абв") == 1


def test_citations_checked_against_context():
    ctx = build_context(HITS)
    ok = check_citations("Срок 2–7 дней [faq-delivery].", ctx)
    assert ok.ok and ok.cited == ["faq-delivery"]
    bad = check_citations("Гарантия год [faq-warranty], доставка [faq-delivery].", ctx)
    assert not bad.ok and bad.unknown == ["faq-warranty"]
    assert not check_citations("Без ссылок.", ctx).ok


def test_hallucinated_citation_is_marked_in_answer():
    llm = FakeLLM("Гарантия 12 месяцев [faq-warranty].")
    ans = answer_question("гарантия?", HITS, llm)
    assert ans.unknown_citations == ["faq-warranty"] and not ans.grounded
    assert "[faq-warranty — нет в источниках]" in ans.answer
    assert "[faq-delivery] Доставка" in llm.seen[2]


def test_extractive_answer_cites_only_context():
    ans = answer_question("За сколько дней доставка в регионы?", HITS, ExtractiveLLM())
    assert ans.grounded and ans.citations[0] == "faq-delivery"
    assert "2–7" in ans.answer


def test_no_hits_no_answer():
    ans = answer_question("что угодно", [], ExtractiveLLM())
    assert ans.answer == NO_ANSWER and not ans.grounded


class StubBackend:
    def vector_search(self, qvec, k, filters):
        self.filters = filters
        return HITS

    def fulltext_search(self, question, k, filters):
        return HITS[:1]


class StubEmbedder:
    name, dim = "stub", 1

    def embed_query(self, text):
        return [1.0]


def test_api_ask_returns_checked_citations():
    backend = StubBackend()
    app = create_app(Retriever(backend, StubEmbedder()), FakeLLM("Срок 2–7 дней [faq-delivery]. Ещё [nope]."))
    with TestClient(app) as client:
        r = client.post("/ask", json={"question": "доставка", "make": "Kia"})
    assert r.status_code == 200
    body = r.json()
    assert body["citations"] == ["faq-delivery", "nope"] and body["unknown_citations"] == ["nope"]
    assert body["grounded"] is False and backend.filters.make == "Kia"
    assert {s["doc_id"] for s in body["sources"]} == {"faq-delivery", "faq-returns"}


def test_extractive_skips_duplicate_sentences_from_overlap():
    dup = [
        HITS[0],
        Hit("faq-delivery#1", "faq-delivery", "Доставка", "Срок 2–7 рабочих дней. Трек приходит в SMS.", 0.5),
    ]
    ans = answer_question("срок доставки дней", dup, ExtractiveLLM())
    assert ans.answer.count("Срок 2–7 рабочих дней.") == 1


def test_extractive_needs_more_than_one_shared_word():
    hits = [Hit("car-x#0", "car-x", "Машина", "Комплект стоит 48 800 ₽.", 0.5)]
    assert answer_question("Сколько стоит доставка на Марс?", hits, ExtractiveLLM()).answer == NO_ANSWER
