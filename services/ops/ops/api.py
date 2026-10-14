"""HTTP для дашборда: поставить задачу и узнать её статус.

Наружу не публикуется — слушает внутреннюю сеть docker. Даже там без ключа
X-Ops-Key не отвечает ничего, а без заданного OPS_API_KEY закрыто всё.
"""

import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ops import config, queue
from ops.db import make_engine, make_sessionmaker
from ops.models import Job
from ops.tasks import TASKS

app = FastAPI(title="TMGoods ops", docs_url=None, redoc_url=None, openapi_url=None)
engine = make_engine()
sessions = make_sessionmaker(engine)


def require_key(x_ops_key: str = Header(default="")) -> None:
    if not config.OPS_API_KEY or not secrets.compare_digest(x_ops_key, config.OPS_API_KEY):
        raise HTTPException(status_code=401)


class JobIn(BaseModel):
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=10, ge=-100, le=100)
    idempotency_key: str | None = Field(default=None, max_length=200)


def _out(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "result": job.result,
        "error": job.last_error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", dependencies=[Depends(require_key)])
async def create_job(body: JobIn) -> dict[str, Any]:
    if body.kind not in TASKS:
        raise HTTPException(status_code=422, detail=f"нет задачи {body.kind}")
    async with sessions() as s:
        job, created = await queue.enqueue(
            s, body.kind, body.payload, priority=body.priority, idempotency_key=body.idempotency_key
        )
        return {**_out(job), "created": created}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_key)])
async def get_job(job_id: int) -> dict[str, Any]:
    async with sessions() as s:
        job = await s.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404)
        return _out(job)
