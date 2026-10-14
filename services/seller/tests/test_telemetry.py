from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from seller.telemetry import TracingCallback, setup_tracing

PRICES = {"scripted": (1.0, 5.0)}  # условные цены за миллион токенов, только для теста


def traced(seller, text_or_command, thread="t"):
    exporter = InMemorySpanExporter()
    provider = setup_tracing("seller-test")
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    callback = TracingCallback(provider.get_tracer("seller"), PRICES)
    payload = {"messages": [HumanMessage(text_or_command)]} if isinstance(text_or_command, str) else text_or_command
    seller.invoke(payload, {"configurable": {"thread_id": thread}, "callbacks": [callback]})
    return {s.name: s for s in exporter.get_finished_spans()}, exporter.get_finished_spans()


def usage(message: AIMessage, tokens_in: int, tokens_out: int) -> AIMessage:
    message.usage_metadata = {
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "total_tokens": tokens_in + tokens_out,
    }
    return message


def tool_call(name, args):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": "c1"}])


def test_turn_trace_has_nodes_model_and_tool(make_seller):
    seller, _ = make_seller(
        usage(tool_call("find_kit_for_car", {"car_make": "Kia", "car_model": "Rio"}), 1200, 40),
        usage(AIMessage("Под Kia Rio есть комплект за 36 860 ₽."), 2500, 90),
    )
    by_name, spans = traced(seller, "kia rio")

    turn = by_name["seller.turn"]
    assert turn.attributes["seller.agent"] == "product_finder"
    assert turn.attributes["seller.routing"] == "rule"
    assert turn.attributes["gen_ai.usage.input_tokens"] == 3700
    assert turn.attributes["gen_ai.usage.output_tokens"] == 130
    assert turn.attributes["seller.cost"] == round((3700 * 1 + 130 * 5) / 1_000_000, 6)

    names = [s.name for s in spans]
    assert names.count("chat scripted") == 2 and "tool find_kit_for_car" in names
    assert {"node route", "node agent", "node tools"} <= set(names)
    # Всё в одном трейсе, а вызов инструмента вложен в узел tools.
    assert {s.context.trace_id for s in spans} == {turn.context.trace_id}
    assert by_name["tool find_kit_for_car"].parent.span_id == by_name["node tools"].context.span_id


def test_interrupt_is_not_an_error(make_seller):
    order = {"customer_name": "Иван", "customer_phone": "79000000000", "items": [{"sku": "kit-22", "quantity": 1}]}
    seller, _ = make_seller(tool_call("place_order", order), AIMessage("Заявка №1 принята."))
    by_name, _ = traced(seller, "беру", thread="o")
    tool = by_name["tool place_order"]
    assert tool.attributes["seller.interrupted"] is True
    assert tool.status.is_ok
    by_name, _ = traced(seller, Command(resume={"approved": True}), thread="o")
    assert (
        by_name["tool place_order"].status.is_ok and "seller.interrupted" not in by_name["tool place_order"].attributes
    )


def test_unknown_price_writes_tokens_without_cost(make_seller):
    seller, _ = make_seller(usage(AIMessage("Привет! Какое авто?"), 300, 12))
    exporter = InMemorySpanExporter()
    provider = setup_tracing("seller-test")
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    seller.invoke(
        {"messages": [HumanMessage("привет")]},
        {"configurable": {"thread_id": "p"}, "callbacks": [TracingCallback(provider.get_tracer("seller"))]},
    )
    turn = next(s for s in exporter.get_finished_spans() if s.name == "seller.turn")
    assert turn.attributes["gen_ai.usage.input_tokens"] == 300 and "seller.cost" not in turn.attributes
