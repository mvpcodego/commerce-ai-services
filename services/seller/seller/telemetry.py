"""Трейсы OpenTelemetry для графа продавца: один ход диалога — один трейс.

    seller.turn                        агент, способ маршрутизации, токены и стоимость хода
    ├── node route
    ├── node agent
    │   └── chat <модель>              gen_ai.usage.input_tokens / output_tokens, seller.cost
    ├── node tools
    │   └── tool find_kit_for_car
    └── node agent
        └── chat <модель>

Подключается колбэком LangChain, сам граф о трейсинге не знает:
    graph.invoke(state, {"callbacks": [TracingCallback(tracer, prices)], ...})

Цены моделей передаются снаружи (за миллион токенов, вход и выход): у каждого провайдера
свои и они меняются. Нет цены для модели — стоимость не пишется, токены пишутся всегда.
"""

import os
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Status, StatusCode, Tracer

Prices = dict[str, tuple[float, float]]


def setup_tracing(service_name: str = "seller", exporter: SpanExporter | None = None) -> TracerProvider:
    """Провайдер трейсов. Без экспортёра и без OTEL_EXPORTER_OTLP_ENDPOINT спаны никуда не уходят."""
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is None and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        exporter = OTLPSpanExporter()
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def _is_interrupt(error: BaseException) -> bool:
    # Остановка перед заказом — штатное поведение графа, а не ошибка.
    return type(error).__name__ in {"GraphInterrupt", "NodeInterrupt"}


class TracingCallback(BaseCallbackHandler):
    def __init__(self, tracer: Tracer, prices: Prices | None = None) -> None:
        self.tracer = tracer
        self.prices = prices or {}
        self.spans: dict[UUID, Span] = {}
        self.parents: dict[UUID, UUID | None] = {}
        self.turn: Span | None = None
        self.totals = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}

    # Внутренние runnable LangGraph (запись каналов, функции переходов) спанов не получают,
    # но их потомки должны повиснуть на ближайшем настоящем спане.
    def _parent_span(self, parent_run_id: UUID | None) -> Span | None:
        while parent_run_id is not None:
            if parent_run_id in self.spans:
                return self.spans[parent_run_id]
            parent_run_id = self.parents.get(parent_run_id)
        return None

    def _start(self, run_id: UUID, parent_run_id: UUID | None, name: str, **attributes: Any) -> Span:
        parent = self._parent_span(parent_run_id)
        context = trace.set_span_in_context(parent) if parent else None
        span = self.tracer.start_span(name, context=context, attributes=attributes)
        self.spans[run_id] = span
        return span

    def _end(self, run_id: UUID, error: BaseException | None = None) -> Span | None:
        span = self.spans.pop(run_id, None)
        if span is None:
            return None
        if error is not None:
            if _is_interrupt(error):
                span.set_attribute("seller.interrupted", True)
            else:
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR, str(error)))
        span.end()
        return span

    def on_chain_start(self, serialized, inputs, *, run_id, parent_run_id=None, metadata=None, **kwargs):
        self.parents[run_id] = parent_run_id
        node = (metadata or {}).get("langgraph_node")
        if parent_run_id is None:
            self.turn = self._start(run_id, None, "seller.turn")
            self.totals = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}
        elif node and kwargs.get("name") == node:
            self._start(run_id, parent_run_id, f"node {node}", **{"langgraph.node": node})

    def on_chain_end(self, outputs, *, run_id, parent_run_id=None, **kwargs):
        if parent_run_id is None and self.turn is not None and isinstance(outputs, dict):
            for key in ("agent", "routing", "reason"):
                if outputs.get(key):
                    self.turn.set_attribute(f"seller.{key}", str(outputs[key]))
            self.turn.set_attribute("gen_ai.usage.input_tokens", self.totals["input_tokens"])
            self.turn.set_attribute("gen_ai.usage.output_tokens", self.totals["output_tokens"])
            if self.totals["cost"]:
                self.turn.set_attribute("seller.cost", round(self.totals["cost"], 6))
        self._end(run_id)

    def on_chain_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._end(run_id, error)

    def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, metadata=None, **kwargs):
        model = (metadata or {}).get("ls_model_name") or (serialized or {}).get("name") or "model"
        self._start(
            run_id,
            parent_run_id,
            f"chat {model}",
            **{"gen_ai.operation.name": "chat", "gen_ai.request.model": model, "seller.messages": len(messages[0])},
        )

    def on_llm_end(self, response, *, run_id, parent_run_id=None, **kwargs):
        span = self.spans.get(run_id)
        message = getattr(response.generations[0][0], "message", None) if response.generations else None
        usage = getattr(message, "usage_metadata", None) or {}
        if span is not None and usage:
            tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            span.set_attribute("gen_ai.usage.input_tokens", tokens_in)
            span.set_attribute("gen_ai.usage.output_tokens", tokens_out)
            self.totals["input_tokens"] += tokens_in
            self.totals["output_tokens"] += tokens_out
            model = span.attributes.get("gen_ai.request.model")  # type: ignore[attr-defined]
            if model in self.prices:
                price_in, price_out = self.prices[model]
                cost = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
                span.set_attribute("seller.cost", round(cost, 6))
                self.totals["cost"] += cost
        if span is not None and getattr(message, "tool_calls", None):
            span.set_attribute("seller.tool_calls", [c["name"] for c in message.tool_calls])
        self._end(run_id)

    def on_llm_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._end(run_id, error)

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._start(run_id, parent_run_id, f"tool {name}", **{"gen_ai.tool.name": name})

    def on_tool_end(self, output, *, run_id, parent_run_id=None, **kwargs):
        self._end(run_id)

    def on_tool_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self._end(run_id, error)
