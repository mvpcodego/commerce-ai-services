#!/usr/bin/env sh
# Генерация кода из proto/ops_rpc.proto в ops/rpc/. Запуск из services/ops: sh proto/generate.sh
set -e
uv run python -m grpc_tools.protoc -I proto --python_out=ops/rpc --pyi_out=ops/rpc --grpc_python_out=ops/rpc proto/ops_rpc.proto
# protoc пишет абсолютный импорт соседнего модуля — внутри пакета ops.rpc он не находится.
sed -i.bak 's/^import ops_rpc_pb2 as/from ops.rpc import ops_rpc_pb2 as/' ops/rpc/ops_rpc_pb2_grpc.py && rm ops/rpc/ops_rpc_pb2_grpc.py.bak
