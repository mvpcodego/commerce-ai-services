from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command


def run(seller, text, thread="t1"):
    return seller.invoke({"messages": [HumanMessage(text)]}, {"configurable": {"thread_id": thread}})


def call(name, args, id="c1"):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": id}])


def test_rule_routing_skips_classifier(make_seller):
    seller, model = make_seller(AIMessage("Привет! Какое авто?"))
    state = run(seller, "привет")
    assert (state["agent"], state["routing"]) == ("greeter", "rule")
    assert len(model.calls) == 1  # только агент, классификатор не вызывался
    assert state["messages"][-1].content == "Привет! Какое авто?"


def test_ambiguous_message_goes_through_classifier(make_seller):
    seller, model = make_seller(AIMessage("objection_handler"), AIMessage("Понимаю. С чем сравниваете?"))
    state = run(seller, "дорого")
    assert (state["agent"], state["routing"]) == ("objection_handler", "classifier")
    assert len(model.calls) == 2


def test_classifier_nonsense_falls_back_to_greeter(make_seller):
    seller, _ = make_seller(AIMessage("не знаю"), AIMessage("Какое у вас авто?"))
    assert run(seller, "ну такое")["agent"] == "greeter"


def test_agent_uses_catalog_tool(make_seller):
    seller, model = make_seller(
        call("find_kit_for_car", {"car_make": "Kia", "car_model": "Rio"}),
        AIMessage('Под Kia Rio есть комплект Aurio S1 12.3" за 36 860 ₽. [> Оформить заказ]'),
    )
    state = run(seller, "kia rio")
    tool_result = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert '"found": true' in tool_result.content and "kit-22" in tool_result.content
    # Ответ инструмента ушёл модели вторым вызовом.
    assert any(isinstance(m, ToolMessage) for m in model.calls[1])


def test_foreign_tool_is_not_executed(make_seller, catalog):
    # Приветствию place_order не положен: граф отказывает, модель отвечает заново.
    seller, _ = make_seller(
        call("place_order", {"customer_name": "Иван", "customer_phone": "79000000000", "items": []}),
        AIMessage("Какое у вас авто?"),
    )
    state = run(seller, "привет")
    refusal = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert "недоступен" in refusal.content and catalog.orders == []


ORDER = {"customer_name": "Иван", "customer_phone": "79000000000", "items": [{"sku": "kit-22", "quantity": 1}]}


def test_order_waits_for_human_and_saves_after_approval(make_seller, catalog):
    seller, _ = make_seller(call("place_order", ORDER), AIMessage("Заявка №1 принята, менеджер перезвонит."))
    config = {"configurable": {"thread_id": "order"}}
    state = seller.invoke({"messages": [HumanMessage("беру, оформляем")]}, config)

    pending = state["__interrupt__"][0].value
    assert pending["total"] == 36860 and pending["phone"] == "79000000000"
    assert catalog.orders == []  # до решения человека ничего не записано

    state = seller.invoke(Command(resume={"approved": True}), config)
    assert len(catalog.orders) == 1 and catalog.orders[0]["total"] == 36860
    assert state["messages"][-1].content.startswith("Заявка №1")


def test_rejected_order_is_not_saved(make_seller, catalog):
    seller, _ = make_seller(call("place_order", ORDER), AIMessage("Уточню у менеджера и вернусь."))
    config = {"configurable": {"thread_id": "order"}}
    seller.invoke({"messages": [HumanMessage("беру")]}, config)
    state = seller.invoke(Command(resume={"approved": False, "reason": "нет телефона"}), config)
    result = next(m for m in state["messages"] if isinstance(m, ToolMessage))
    assert catalog.orders == [] and "нет телефона" in result.content


def test_checkpoint_keeps_dialog_per_thread(make_seller):
    seller, _ = make_seller(AIMessage("Какое авто?"), AIMessage("Подберу."), AIMessage("Какое авто?"))
    run(seller, "привет", thread="a")
    state = run(seller, "что у вас есть?", thread="a")
    assert [m.content for m in state["messages"] if isinstance(m, HumanMessage)] == ["привет", "что у вас есть?"]
    other = run(seller, "привет", thread="b")
    assert len(other["messages"]) == 2  # чужой диалог не подмешивается


def test_order_resumes_in_new_process(tmp_path, catalog):
    """Клиент нажал «беру» вечером, менеджер подтвердил утром: между ними сервис перезапускался."""
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver

    from seller.graph import build_graph
    from tests.conftest import ScriptedModel

    db = tmp_path / "checkpoints.sqlite"
    config = {"configurable": {"thread_id": "night-order"}}

    with sqlite3.connect(db, check_same_thread=False) as conn:
        evening = build_graph(
            ScriptedModel(responses=[call("place_order", ORDER)], calls=[]), catalog, SqliteSaver(conn)
        )
        evening.invoke({"messages": [HumanMessage("беру")]}, config)

    with sqlite3.connect(db, check_same_thread=False) as conn:
        morning = build_graph(
            ScriptedModel(responses=[AIMessage("Заявка №1 принята.")], calls=[]), catalog, SqliteSaver(conn)
        )
        assert morning.get_state(config).next == ("tools",)  # граф помнит, где остановился
        morning.invoke(Command(resume={"approved": True}), config)

    assert len(catalog.orders) == 1
