import asyncio
import json

import grpc
import pytest

from ops import config, queue
from ops.grpc_server import make_server
from ops.rpc import ops_rpc_pb2 as pb
from ops.rpc import ops_rpc_pb2_grpc as rpc

KEY = (("x-ops-key", "test-key"),)


@pytest.fixture
async def stub(sessions, monkeypatch):
    monkeypatch.setattr(config, "OPS_API_KEY", "test-key")
    server, port = make_server(sessions, "127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    yield rpc.OpsStub(channel)
    await channel.close()
    await server.stop(None)


async def test_enqueue_is_idempotent_by_key(stub):
    request = pb.EnqueueJobRequest(kind="export_orders", payload_json='{"day": "2026-10-13"}', idempotency_key="exp:13")
    first = await stub.EnqueueJob(request, metadata=KEY)
    again = await stub.EnqueueJob(request, metadata=KEY)
    assert first.created and not again.created and first.id == again.id
    assert (await stub.GetJob(pb.GetJobRequest(id=first.id), metadata=KEY)).status == "queued"


@pytest.mark.parametrize(
    "request_, code",
    [
        (pb.EnqueueJobRequest(kind="rm_rf"), grpc.StatusCode.INVALID_ARGUMENT),
        (pb.EnqueueJobRequest(kind="procurement", payload_json="[1]"), grpc.StatusCode.INVALID_ARGUMENT),
    ],
)
async def test_bad_requests(stub, request_, code):
    with pytest.raises(grpc.aio.AioRpcError) as err:
        await stub.EnqueueJob(request_, metadata=KEY)
    assert err.value.code() == code


async def test_missing_job(stub):
    with pytest.raises(grpc.aio.AioRpcError) as err:
        await stub.GetJob(pb.GetJobRequest(id=999), metadata=KEY)
    assert err.value.code() == grpc.StatusCode.NOT_FOUND


async def test_without_key_nothing_works(stub):
    for call in (
        stub.GetJob(pb.GetJobRequest(id=1)),
        stub.GetJob(pb.GetJobRequest(id=1), metadata=(("x-ops-key", "wrong"),)),
    ):
        with pytest.raises(grpc.aio.AioRpcError) as err:
            await call
        assert err.value.code() == grpc.StatusCode.UNAUTHENTICATED
    with pytest.raises(grpc.aio.AioRpcError) as err:
        async for _ in stub.WatchJob(pb.GetJobRequest(id=1)):
            pass
    assert err.value.code() == grpc.StatusCode.UNAUTHENTICATED


async def test_watch_streams_until_done(stub, sessions):
    job = await stub.EnqueueJob(pb.EnqueueJobRequest(kind="procurement"), metadata=KEY)
    seen = []

    async def watch():
        async for update in stub.WatchJob(pb.GetJobRequest(id=job.id), metadata=KEY):
            seen.append(update.status)

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0.3)
    async with sessions() as s:
        claimed = await queue.claim(s, "test-worker")
    await asyncio.sleep(0.8)
    async with sessions() as s:
        await queue.complete(s, claimed, {"positions": 16})
    await asyncio.wait_for(watcher, 5)  # поток закрылся сам на конечном статусе

    assert seen == ["queued", "running", "done"]
    final = await stub.GetJob(pb.GetJobRequest(id=job.id), metadata=KEY)
    assert json.loads(final.result_json) == {"positions": 16}
