"""Чанкинг по предложениям с перекрытием.

Абзацы режутся на предложения, предложения набираются в чанк до max_chars. Следующий чанк
начинается с последних overlap предложений предыдущего — факт на границе не теряется.
Заголовок документа в чанк не входит: он добавляется при индексации (см. Chunk.content).
"""

import re
from dataclasses import dataclass

from rag.corpus import Doc

SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[«\"(А-ЯЁA-Z0-9])")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    ord: int
    title: str
    text: str
    doc_type: str
    make: str | None
    model: str | None

    @property
    def content(self) -> str:
        """Текст для эмбеддинга и полнотекста: заголовок даёт чанку контекст документа."""
        return f"{self.title}. {self.text}"


def split_sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n\s*\n|\n", text):
        out += [s.strip() for s in SENTENCE.split(para.strip()) if s.strip()]
    return out


def chunk_doc(doc: Doc, max_chars: int = 500, overlap: int = 1) -> list[Chunk]:
    if overlap < 0:
        raise ValueError("overlap >= 0")
    sents = split_sentences(doc.text)
    groups: list[list[str]] = []
    cur: list[str] = []
    fresh = 0  # сколько предложений в cur добавлено после перекрытия
    for s in sents:
        if cur and fresh and len(" ".join(cur + [s])) > max_chars:
            groups.append(cur)
            cur = cur[-overlap:] if overlap else []
            fresh = 0
            # перекрытие не должно само по себе переполнять чанк
            while cur and len(" ".join(cur + [s])) > max_chars:
                cur = cur[1:]
        cur.append(s)
        fresh += 1
    if cur and fresh:
        groups.append(cur)
    return [
        Chunk(f"{doc.doc_id}#{i}", doc.doc_id, i, doc.title, " ".join(g), doc.doc_type, doc.make, doc.model)
        for i, g in enumerate(groups)
    ]


def chunk_corpus(docs: list[Doc], max_chars: int = 500, overlap: int = 1) -> list[Chunk]:
    return [c for d in docs for c in chunk_doc(d, max_chars, overlap)]
