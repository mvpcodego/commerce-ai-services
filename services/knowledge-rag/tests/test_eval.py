import math

from rag.embed import HashEmbedder
from rag.eval import evaluate, ndcg_at, recall_at, reciprocal_rank
from rag.retrieval import Retriever


def test_metrics_on_hand_examples():
    ranked = ["x", "a", "y", "b", "z"]
    rel = {"a", "b"}
    assert recall_at(ranked, rel, 5) == 1.0
    assert recall_at(ranked, rel, 2) == 0.5
    assert reciprocal_rank(ranked, rel) == 0.5
    expected = (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    assert abs(ndcg_at(ranked, rel, 5) - expected) < 1e-12
    assert ndcg_at(["a", "b"], rel, 5) == 1.0
    assert reciprocal_rank(["x"], rel) == 0.0
    # recall нормирован на min(|rel|, k): 11 релевантных, 5 из них в топ-5 — это 1.0
    assert recall_at(list("abcde"), set("abcdefghijk"), 5) == 1.0


def test_eval_on_small_set_against_db(store):
    questions = [
        {"question": "Переходная рамка Kia Rio", "relevant": ["car-kia-rio"]},
        {"question": "прошивка с флешки FAT32", "relevant": ["faq-firmware"]},
        {"question": "Набор SET-006", "relevant": ["bundle-set-006"]},
    ]
    res = evaluate(Retriever(store, HashEmbedder()), questions, k=5)
    assert set(res) == {"vector", "fulltext", "hybrid"}
    assert res["fulltext"]["recall@5"] == 1.0  # точные слова и артикулы наборов — сильная сторона полнотекста
    for v in res.values():
        assert 0 <= v["mrr"] <= 1 and 0 <= v["ndcg@5"] <= 1
