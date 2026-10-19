"""HTTP: POST /ask — гибридный поиск + ответ с цитатами, POST /search — только поиск.
RAG_RERANK=1 включает кросс-энкодер поверх гибрида (модель ~0.6 ГБ скачивается при старте).

uv run uvicorn rag.api:app --port 8095
"""

import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from pydantic import BaseModel, Field

from rag.answer import LLM, answer_question, make_llm
from rag.embed import make_embedder
from rag.retrieval import CrossEncoderReranker, Retriever
from rag.store import Filters, Store


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    make: str | None = None
    model: str | None = None
    k: int = Field(8, ge=1, le=30)
    budget_tokens: int = Field(1200, ge=100, le=8000)


class SearchIn(AskIn):
    mode: str = Field("hybrid", pattern="^(hybrid|vector|fulltext|rerank)$")


def create_app(retriever: Retriever | None = None, llm: LLM | None = None) -> FastAPI:
    state: dict = {"retriever": retriever, "llm": llm}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["retriever"] is None:
            store = Store.connect()
            store.migrate()
            reranker = CrossEncoderReranker() if os.environ.get("RAG_RERANK") == "1" else None
            state["retriever"] = Retriever(store, make_embedder(store.embedder_name()), reranker=reranker)
        state["llm"] = state["llm"] or make_llm()
        yield

    app = FastAPI(title="knowledge-rag", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "embedder": state["retriever"].embedder.name, "llm": state["llm"].name}

    @app.post("/search")
    def search(body: SearchIn) -> list[dict]:
        hits = state["retriever"].search(body.question, body.mode, body.k, Filters(body.make, body.model))
        return [asdict(h) for h in hits]

    @app.post("/ask")
    def ask(body: AskIn) -> dict:
        r = state["retriever"]
        hits = r.search(body.question, "rerank" if r.reranker else "hybrid", body.k, Filters(body.make, body.model))
        return asdict(answer_question(body.question, hits, state["llm"], body.budget_tokens))

    return app


app = create_app()
