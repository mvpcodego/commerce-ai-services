"""Ответ «строго по источнику»: контекст с бюджетом токенов, модель за абстракцией, проверка цитат.

По умолчанию модель не вызывается: ExtractiveLLM собирает ответ из предложений контекста
и ставит цитату к каждому. Настоящая модель включается переменной RAG_LLM=openai|anthropic.
"""

import math
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from rag.chunking import split_sentences
from rag.store import Hit

CITATION = re.compile(r"\[([a-z0-9][a-z0-9-]*)\]")
NO_ANSWER = "В базе знаний нет ответа на этот вопрос."

SYSTEM = (
    "Ты консультант магазина автомагнитол. Отвечай только по фрагментам из блока ИСТОЧНИКИ. "
    "После каждого утверждения ставь ссылку на источник в квадратных скобках, например [faq-delivery]. "
    "Используй только идентификаторы из ИСТОЧНИКОВ. Если ответа во фрагментах нет, ответь ровно: " + NO_ANSWER
)


def approx_tokens(text: str) -> int:
    """Грубая оценка: в русском тексте у BPE-токенизаторов выходит ~3 символа на токен."""
    return math.ceil(len(text) / 3)


@dataclass
class Context:
    hits: list[Hit]
    tokens: int
    dropped: int  # сколько найденных фрагментов не влезло в бюджет

    def render(self) -> str:
        return "\n\n".join(f"[{h.doc_id}] {h.title}\n{h.text}" for h in self.hits)

    @property
    def doc_ids(self) -> set[str]:
        return {h.doc_id for h in self.hits}


def build_context(hits: list[Hit], budget_tokens: int = 1200) -> Context:
    """Берём фрагменты в порядке ранга, пока помещаются. Фрагмент целиком или никак:
    обрезанное посередине предложение — плохой источник для цитаты."""
    taken, used = [], 0
    for h in hits:
        cost = approx_tokens(f"[{h.doc_id}] {h.title}\n{h.text}")
        if used + cost > budget_tokens:
            continue
        taken.append(h)
        used += cost
    return Context(taken, used, len(hits) - len(taken))


@dataclass
class CitationCheck:
    cited: list[str]
    unknown: list[str]  # цитаты на документы, которых нет в контексте

    @property
    def ok(self) -> bool:
        return bool(self.cited) and not self.unknown


def check_citations(answer: str, context: Context) -> CitationCheck:
    cited = list(dict.fromkeys(CITATION.findall(answer)))
    return CitationCheck(cited, [c for c in cited if c not in context.doc_ids])


class LLM(Protocol):
    name: str

    def complete(self, system: str, question: str, context: Context) -> str: ...


STOP = {
    "как",
    "что",
    "для",
    "или",
    "это",
    "есть",
    "ли",
    "мне",
    "мой",
    "моей",
    "сколь",
    "какой",
    "какая",
    "можно",
    "нужно",
    "нужна",
    "если",
    "при",
    "все",
    "вас",
    "наш",
}


def _words(text: str) -> set[str]:
    """Грубые основы: первые 5 букв слова. Без морфологии, но «доставка/доставки» совпадают."""
    return {
        w[:5] for w in re.findall(r"[0-9a-zа-яё]+", text.lower()) if len(w) > 2 and w not in STOP and w[:5] not in STOP
    }


class ExtractiveLLM:
    """Без генерации: до max_sentences предложений контекста с наибольшим пересечением основ слов
    с вопросом, у каждого — цитата его документа. Ничего не придумывает, но и не обобщает,
    и смысл вопроса не понимает: «нет ответа» он скажет только при малом пересечении слов."""

    name = "extractive"

    def __init__(self, max_sentences: int = 3, min_overlap: int = 2) -> None:
        self.max_sentences = max_sentences
        self.min_overlap = min_overlap  # одно общее слово («стоит») — ещё не ответ

    def complete(self, system: str, question: str, context: Context) -> str:
        q = _words(question)
        scored, seen = [], set()
        for rank, h in enumerate(context.hits):
            title = _words(h.title)
            for i, s in enumerate(split_sentences(h.text)):
                own = q & _words(s)
                # Заголовок документа — контекст предложения («Доставка по России» + «в регионы … 2–7 дней»),
                # но хотя бы одно слово вопроса должно быть в самом предложении.
                overlap = len(own | (q & title)) if own else 0
                # соседние чанки перекрываются — одно предложение дважды не берём
                if overlap >= self.min_overlap and s not in seen:
                    seen.add(s)
                    scored.append((-overlap, rank, i, s, h.doc_id))
        if not scored:
            return NO_ANSWER
        best = sorted(scored)[: self.max_sentences]
        return " ".join(f"{s} [{doc}]" for *_, s, doc in best)


class OpenAICompatLLM:
    name = "openai-compatible"

    def __init__(self) -> None:
        self.url = os.environ.get("RAG_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        self.key = os.environ["RAG_LLM_API_KEY"]
        self.model = os.environ["RAG_LLM_MODEL"]

    def complete(self, system: str, question: str, context: Context) -> str:
        r = httpx.post(
            self.url,
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"ИСТОЧНИКИ:\n{context.render()}\n\nВОПРОС: {question}"},
                ],
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class AnthropicLLM:
    name = "anthropic"

    def __init__(self) -> None:
        self.key = os.environ["ANTHROPIC_API_KEY"]
        self.model = os.environ["RAG_LLM_MODEL"]

    def complete(self, system: str, question: str, context: Context) -> str:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
            json={
                "model": self.model,
                "max_tokens": 600,
                "system": system,
                "messages": [{"role": "user", "content": f"ИСТОЧНИКИ:\n{context.render()}\n\nВОПРОС: {question}"}],
            },
            timeout=60,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])


def make_llm(kind: str | None = None) -> LLM:
    kind = kind or os.environ.get("RAG_LLM", "extractive")
    return {"extractive": ExtractiveLLM, "openai": OpenAICompatLLM, "anthropic": AnthropicLLM}[kind]()


@dataclass
class Answer:
    answer: str
    citations: list[str]
    unknown_citations: list[str]
    grounded: bool
    sources: list[dict] = field(default_factory=list)
    context_tokens: int = 0
    dropped_hits: int = 0
    llm: str = ""


def answer_question(question: str, hits: list[Hit], llm: LLM, budget_tokens: int = 1200) -> Answer:
    ctx = build_context(hits, budget_tokens)
    if not ctx.hits:
        return Answer(NO_ANSWER, [], [], False, llm=llm.name, dropped_hits=ctx.dropped)
    text = llm.complete(SYSTEM, question, ctx)
    check = check_citations(text, ctx)
    # Помечаем выдуманные цитаты прямо в тексте, чтобы их было видно и без разбора JSON.
    for bad in check.unknown:
        text = text.replace(f"[{bad}]", f"[{bad} — нет в источниках]")
    return Answer(
        answer=text,
        citations=check.cited,
        unknown_citations=check.unknown,
        grounded=check.ok or text.strip() == NO_ANSWER,
        sources=[
            {"doc_id": h.doc_id, "chunk_id": h.chunk_id, "title": h.title, "score": round(h.score, 5)} for h in ctx.hits
        ],
        context_tokens=ctx.tokens,
        dropped_hits=ctx.dropped,
        llm=llm.name,
    )
