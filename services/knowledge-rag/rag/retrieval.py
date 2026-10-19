"""Гибридный поиск: вектор + полнотекст, объединённые Reciprocal Rank Fusion.

RRF складывает 1 / (k + rank) по всем спискам. Сырые оценки (косинус и ts_rank) в разных
шкалах и не сравниваются — RRF смотрит только на места, поэтому нормировать их не нужно.
"""

from dataclasses import dataclass, replace
from typing import Protocol

from rag.embed import Embedder
from rag.store import NO_FILTERS, Filters, Hit

RRF_K = 60


class Reranker(Protocol):
    name: str

    def scores(self, question: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Кросс-энкодер читает вопрос и фрагмент вместе — точнее биэнкодера, но дороже,
    поэтому переранжирует только верх гибридного списка. Мультиязычная, int8, ~0.6 ГБ."""

    name = "BAAI/bge-reranker-v2-m3-int8"

    def __init__(self) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(self.name)

    def scores(self, question: str, texts: list[str]) -> list[float]:
        return list(self._model.rerank(question, texts, batch_size=16))


class Backend(Protocol):
    def vector_search(self, qvec: list[float], k: int, filters: Filters) -> list[Hit]: ...

    def fulltext_search(self, question: str, k: int, filters: Filters) -> list[Hit]: ...


def rrf(rankings: list[list[Hit]], k: int = RRF_K) -> list[Hit]:
    scores: dict[str, float] = {}
    first: dict[str, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            first.setdefault(hit.chunk_id, hit)
    order = sorted(scores, key=lambda cid: (-scores[cid], cid))
    return [replace(first[cid], score=scores[cid]) for cid in order]


def doc_ranking(hits: list[Hit]) -> list[str]:
    """Чанки → документы: место документа = место его лучшего чанка."""
    return list(dict.fromkeys(h.doc_id for h in hits))


@dataclass
class Retriever:
    backend: Backend
    embedder: Embedder
    candidates: int = 30  # сколько берём из каждого списка до слияния
    reranker: Reranker | None = None
    rerank_top: int = 20  # сколько чанков гибридного списка отдаём кросс-энкодеру

    def search(self, question: str, mode: str = "hybrid", k: int = 10, filters: Filters = NO_FILTERS) -> list[Hit]:
        # Машина, выбранная фильтром, — часть вопроса: «какая рамка нужна?» на странице Haval Jolion
        # означает «какая рамка нужна для Haval Jolion?». Без этого FAQ про рамки обгоняет карточку машины.
        question = " ".join(x for x in (question, filters.make, filters.model) if x)
        if mode == "vector":
            return self.backend.vector_search(self.embedder.embed_query(question), k, filters)
        if mode == "fulltext":
            return self.backend.fulltext_search(question, k, filters)
        if mode not in ("hybrid", "rerank"):
            raise ValueError(f"unknown mode {mode}")
        vec = self.backend.vector_search(self.embedder.embed_query(question), self.candidates, filters)
        fts = self.backend.fulltext_search(question, self.candidates, filters)
        fused = rrf([vec, fts])
        if mode == "hybrid":
            return fused[:k]
        if self.reranker is None:
            raise ValueError("rerank mode needs a reranker")
        top = fused[: self.rerank_top]
        scores = self.reranker.scores(question, [f"{h.title}. {h.text}" for h in top])
        order = sorted(range(len(top)), key=lambda i: -scores[i])
        return [replace(top[i], score=float(scores[i])) for i in order][:k]
