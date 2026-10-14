from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class EnqueueJobRequest(_message.Message):
    __slots__ = ("kind", "payload_json", "priority", "idempotency_key")
    KIND_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    kind: str
    payload_json: str
    priority: int
    idempotency_key: str
    def __init__(self, kind: _Optional[str] = ..., payload_json: _Optional[str] = ..., priority: _Optional[int] = ..., idempotency_key: _Optional[str] = ...) -> None: ...

class GetJobRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class Job(_message.Message):
    __slots__ = ("id", "kind", "status", "attempts", "result_json", "error", "created")
    ID_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    id: int
    kind: str
    status: str
    attempts: int
    result_json: str
    error: str
    created: bool
    def __init__(self, id: _Optional[int] = ..., kind: _Optional[str] = ..., status: _Optional[str] = ..., attempts: _Optional[int] = ..., result_json: _Optional[str] = ..., error: _Optional[str] = ..., created: _Optional[bool] = ...) -> None: ...
