"""Оценка поиска на размеченном наборе: Recall@5, MRR, nDCG@5 для vector / fulltext / hybrid
(и rerank — hybrid + кросс-энкодер, с флагом --rerank).

Метрики считаются по документам (чанки одного документа схлопываются в его лучшее место).
Recall@k нормирован на min(|релевантных|, k): у вопроса с 11 релевантными документами
потолок 5 из 5, а не 5 из 11.

uv run python -m rag.eval [--questions eval/questions.jsonl] [--k 5] [--rerank]
"""

import argparse
import json
import math
from pathlib import Path

from rag.embed import make_embedder
from rag.retrieval import CrossEncoderReranker, Retriever, doc_ranking
from rag.store import Store

QUESTIONS = Path(__file__).resolve().parents[1] / "eval" / "questions.jsonl"
MODES = ("vector", "fulltext", "hybrid", "rerank")


def recall_at(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / min(len(relevant), k)


def reciprocal_rank(ranked: list[str], relevant: set[str]) -> float:
    return next((1.0 / i for i, d in enumerate(ranked, start=1) if d in relevant), 0.0)


def ndcg_at(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(ranked[:k], start=1) if d in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal


def evaluate(retriever: Retriever, questions: list[dict], k: int = 5, depth: int = 30) -> dict[str, dict]:
    """depth — сколько чанков запрашиваем: документов после схлопывания должно хватить на k."""
    out: dict[str, dict] = {}
    for mode in MODES:
        if mode == "rerank" and retriever.reranker is None:
            continue
        r = m = n = 0.0
        misses = []
        for q in questions:
            rel = set(q["relevant"])
            ranked = doc_ranking(retriever.search(q["question"], mode, depth))
            r += recall_at(ranked, rel, k)
            m += reciprocal_rank(ranked, rel)
            n += ndcg_at(ranked, rel, k)
            if not set(ranked[:k]) & rel:
                misses.append(q["question"])
        cnt = len(questions)
        out[mode] = {f"recall@{k}": r / cnt, "mrr": m / cnt, f"ndcg@{k}": n / cnt, "misses": misses}
    return out


def table(res: dict[str, dict], k: int = 5) -> str:
    lines = [
        f"| Режим | Recall@{k} | MRR | nDCG@{k} | Промахи (ни одного релевантного в топ-{k}) |",
        "|---|---|---|---|---|",
    ]
    for mode, v in res.items():
        lines.append(
            f"| {mode} | {v[f'recall@{k}']:.3f} | {v['mrr']:.3f} | {v[f'ndcg@{k}']:.3f} | {len(v['misses'])} |"
        )
    return "\n".join(lines)


def load_questions(path: str | Path = QUESTIONS) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text("utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(QUESTIONS))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--rerank", action="store_true", help="добавить режим hybrid + кросс-энкодер")
    args = ap.parse_args()
    store = Store.connect()
    store.migrate()
    emb = make_embedder(store.embedder_name())
    qs = load_questions(args.questions)
    reranker = CrossEncoderReranker() if args.rerank else None
    res = evaluate(Retriever(store, emb, reranker=reranker), qs, args.k)
    print(f"Эмбеддер: {emb.name}; вопросов: {len(qs)}; документов/чанков: {store.count()}\n")
    print(table(res, args.k))
    for mode, v in res.items():
        for q in v["misses"]:
            print(f"  промах {mode}: {q}")


if __name__ == "__main__":
    main()
