"""gRPC-сервер очереди задач: EnqueueJob, GetJob и стрим WatchJob (proto/ops_rpc.proto).

Ключ проверяет перехватчик до вызова метода — так же, как require_key у REST: без заданного
OPS_API_KEY закрыто всё. Слушает внутреннюю сеть docker без TLS, наружу порт не публикуется.

WatchJob держит поток, пока задача не дойдёт до конечного статуса, и присылает каждую
смену статуса или числа попыток. Внутри сервер опрашивает базу раз в WATCH_INTERVAL;
опрос остаётся на сервере, клиенту достаточно одного соединения.
"""

import asyncio
import json
import secrets
from typing import Any

import grpc
from sqlalchemy.ext.asyncio import async_sessionmaker

from ops import config, queue
from ops.models import Job
from ops.rpc import ops_rpc_pb2 as pb
from ops.rpc import ops_rpc_pb2_grpc as rpc
from ops.tasks import TASKS

PORT = 50051
TERMINAL = {"done", "dead", "expired"}  # failed — не конец: задача ещё будет повторена
WATCH_INTERVAL = 0.5


def _authorized(metadata: Any) -> bool:
    key = dict(metadata or ()).get("x-ops-key", "")
    return bool(config.OPS_API_KEY) and secrets.compare_digest(key, config.OPS_API_KEY)


class KeyInterceptor(grpc.aio.ServerInterceptor):
    async def intercept_service(self, continuation, details):
        handler = await continuation(details)
        if handler is None or _authorized(details.invocation_metadata):
            return handler

        async def deny_unary(request, context):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "нужен ключ x-ops-key")

        async def deny_stream(request, context):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "нужен ключ x-ops-key")
            yield  # pragma: no cover — делает функцию генератором для потокового метода

        if handler.response_streaming:
            return grpc.unary_stream_rpc_method_handler(deny_stream, request_deserializer=handler.request_deserializer)
        return grpc.unary_unary_rpc_method_handler(deny_unary, request_deserializer=handler.request_deserializer)


def _job(job: Job, created: bool = False) -> pb.Job:
    return pb.Job(
        id=job.id, kind=job.kind, status=job.status, attempts=job.attempts,
        result_json=json.dumps(job.result, ensure_ascii=False) if job.result is not None else "",
        error=job.last_error or "", created=created,
    )


class OpsServicer(rpc.OpsServicer):
    def __init__(self, sessions: async_sessionmaker) -> None:
        self.sessions = sessions

    async def EnqueueJob(self, request: pb.EnqueueJobRequest, context) -> pb.Job:
        if request.kind not in TASKS:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"нет задачи {request.kind}")
        try:
            payload = json.loads(request.payload_json or "{}")
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "payload_json должен быть JSON-объектом")
        async with self.sessions() as s:
            job, created = await queue.enqueue(
                s, request.kind, payload, priority=request.priority,
                idempotency_key=request.idempotency_key if request.HasField("idempotency_key") else None,
            )
            return _job(job, created)

    async def _load(self, job_id: int) -> Job | None:
        async with self.sessions() as s:
            return await s.get(Job, job_id, populate_existing=True)

    async def GetJob(self, request: pb.GetJobRequest, context) -> pb.Job:
        job = await self._load(request.id)
        if job is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"задачи {request.id} нет")
        return _job(job)

    async def WatchJob(self, request: pb.GetJobRequest, context):
        last = None
        while True:
            job = await self._load(request.id)
            if job is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"задачи {request.id} нет")
            state = (job.status, job.attempts)
            if state != last:
                last = state
                yield _job(job)
            if job.status in TERMINAL:
                return
            await asyncio.sleep(WATCH_INTERVAL)


def make_server(sessions: async_sessionmaker, address: str = f"[::]:{PORT}") -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server(interceptors=[KeyInterceptor()])
    rpc.add_OpsServicer_to_server(OpsServicer(sessions), server)
    port = server.add_insecure_port(address)
    return server, port


async def main() -> None:
    from ops.db import make_engine, make_sessionmaker

    engine = make_engine()
    server, _ = make_server(make_sessionmaker(engine))
    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
