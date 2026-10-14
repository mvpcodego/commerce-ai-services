"""Шлюз LiteLLM без ключей: мок-ответы вместо провайдера, «упавшая» модель — закрытый порт."""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from seller.gateway import FAST, SMART, CostLedger, make_router, role_models
from seller.graph import build_graph
from tests.conftest import ScriptedModel

DEAD = {"api_base": "http://127.0.0.1:9", "api_key": "test"}  # порт закрыт: соединение рвётся сразу


# Один журнал на все тесты: журнал, подключённый вторым после первых вызовов, событий
# не получал (так и упали первые версии этих тестов). В приложении журнал тоже один на процесс.
LEDGER = CostLedger()


@pytest.fixture
def ledger():
    LEDGER.reset()
    return LEDGER


def deployments(fast_reply: str, smart: dict) -> list[dict]:
    return [
        {"model_name": FAST, "litellm_params": {"model": "anthropic/claude-haiku-4-5", "mock_response": fast_reply}},
        {"model_name": SMART, "litellm_params": {"model": "anthropic/claude-sonnet-4-5", **smart}},
    ]


def seller(router, catalog):
    unused = ScriptedModel(responses=[], calls=[])  # все роли идут через шлюз, эта модель не должна вызываться
    return build_graph(unused, catalog, InMemorySaver(), role_models=role_models(router)), unused


def ask(graph, text):
    return graph.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": text}})


def test_roles_go_to_their_tier(catalog, ledger):
    router = make_router(deployments("Привет! Какое авто?", {"mock_response": "Под Kia Rio есть комплект."}), ledger)
    graph, unused = seller(router, catalog)

    assert ask(graph, "привет")["messages"][-1].content == "Привет! Какое авто?"
    assert ask(graph, "kia rio")["messages"][-1].content == "Под Kia Rio есть комплект."
    assert ledger.by_alias[FAST]["calls"] == 1 and ledger.by_alias[SMART]["calls"] == 1
    assert unused.calls == []


def test_smart_model_down_falls_back_to_fast(catalog, ledger):
    router = make_router(deployments("Подобрал комплект на запасной модели.", DEAD), ledger)
    graph, _ = seller(router, catalog)

    state = ask(graph, "kia rio")  # подбор — роль сильной модели
    assert state["messages"][-1].content == "Подобрал комплект на запасной модели."
    assert ledger.failures[SMART] >= 1  # сбой виден в журнале, а не проглочен
    assert ledger.by_alias[FAST]["calls"] == 1


def test_ledger_counts_money(catalog, ledger):
    router = make_router(deployments("objection_handler", {"mock_response": "-"}), ledger)
    graph, _ = seller(router, catalog)
    ask(graph, "дорого")  # классификатор и агент — оба на быстрой модели
    assert ledger.by_alias[FAST]["calls"] == 2
    assert ledger.by_alias[FAST]["tokens"] > 0 and ledger.total_cost > 0  # цена — из таблицы LiteLLM
