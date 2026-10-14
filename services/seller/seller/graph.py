"""ИИ-продавец как граф состояний на LangGraph.

    START → route ─(правило уверено)──────────→ agent ⇄ tools → END
                  └(неоднозначно)→ classify ─→ agent

route — правила без модели (seller.router). classify — модель отвечает одним словом,
только когда правила не уверены. agent — модель с инструментами своей роли; цикл
agent ⇄ tools идёт, пока модель вызывает инструменты. place_order перед записью
останавливает граф (interrupt) и ждёт решения человека; состояние лежит в чекпоинте,
поэтому продолжить можно из другого процесса по тому же thread_id.
"""

from typing import Annotated

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from seller.catalog import Catalog
from seller.prompts import AGENT_TOOLS, AGENTS, CLASSIFIER
from seller.router import AGENTS as AGENT_TYPES
from seller.router import route_message

HISTORY_FOR_CLASSIFIER = 4


class SellerState(MessagesState):
    agent: str | None
    routing: str  # "rule" или "classifier" — для аналитики маршрутов
    reason: str


def make_tools(catalog: Catalog) -> list:
    @tool
    def find_kit_for_car(car_make: str, car_model: str | None = None) -> dict:
        """Главный инструмент. Клиент назвал автомобиль — вызывай первым. Возвращает комплекты и совместимые допы."""
        return catalog.find_kit_for_car(car_make, car_model)

    @tool
    def get_popular_models(car_make: str) -> dict:
        """Клиент написал только марку — вернёт модели этой марки из каталога."""
        return catalog.popular_models(car_make)

    @tool
    def search_products(query: str, type: str | None = None, limit: int = 10) -> dict:
        """Поиск позиций по названию, артикулу или бренду."""
        return catalog.search_products(query, type, limit)

    @tool
    def get_product_detail(sku: str) -> dict:
        """Характеристики, цена и остаток одной позиции по артикулу."""
        return catalog.product_detail(sku)

    @tool
    def get_fitting_cars(sku: str) -> dict:
        """К каким автомобилям подходит позиция."""
        return catalog.fitting_cars(sku)

    @tool
    def place_order(
        customer_name: str,
        customer_phone: str,
        items: Annotated[list[dict], "Состав: [{sku, quantity}], комплект — sku вида kit-<id>"],
        comment: str = "",
    ) -> dict:
        """Оформить заказ, когда клиент подтвердил состав и назвал имя и телефон."""
        priced = catalog.price_order(items)
        if not priced["items"]:
            return {"error": "Нечего заказывать: все позиции недоступны", "warnings": priced["warnings"]}
        # Граф встаёт здесь до решения человека. Цены в карточке — из каталога, не из диалога.
        decision = interrupt({"action": "place_order", "customer": customer_name, "phone": customer_phone, **priced})
        if not (isinstance(decision, dict) and decision.get("approved")):
            return {"ok": False, "reason": (decision or {}).get("reason", "Заказ не подтверждён менеджером")}
        order = catalog.save_order(priced, {"name": customer_name, "phone": customer_phone, "comment": comment})
        return {"ok": True, "order_id": order["id"], "total": order["total"], "warnings": priced["warnings"]}

    return [find_kit_for_car, get_popular_models, search_products, get_product_detail, get_fitting_cars, place_order]


def _history(messages: list) -> list[tuple[str, str]]:
    return [
        ("user" if isinstance(m, HumanMessage) else "assistant", str(m.content))
        for m in messages
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and m.content)
    ]


def build_graph(
    model: BaseChatModel,
    catalog: Catalog,
    checkpointer: BaseCheckpointSaver | None = None,
    role_models: dict[str, BaseChatModel] | None = None,
):
    """role_models — своя модель для роли («classifier», «greeter», …), например из seller.gateway.
    Роли без своей модели работают на model."""
    role_models = role_models or {}
    tools = make_tools(catalog)
    by_name = {t.name: t for t in tools}
    bound = {
        agent: role_models.get(agent, model).bind_tools([by_name[n] for n in names])
        for agent, names in AGENT_TOOLS.items()
    }
    classifier = role_models.get("classifier", model)

    def route(state: SellerState) -> dict:
        *previous, last = state["messages"]
        decision = route_message(str(last.content), _history(previous))
        if decision.agent and decision.confidence != "low":
            return {"agent": decision.agent, "routing": "rule", "reason": decision.reason}
        return {"agent": None, "routing": "classifier", "reason": decision.reason}

    def classify(state: SellerState) -> dict:
        recent = [m for m in state["messages"] if isinstance(m, (HumanMessage, AIMessage)) and m.content]
        answer = classifier.invoke([SystemMessage(CLASSIFIER), *recent[-HISTORY_FOR_CLASSIFIER - 1 :]])
        text = str(answer.content).strip().lower()
        agent = next((a for a in AGENT_TYPES if a in text), "greeter")  # непонятный ответ — безопасный greeter
        return {"agent": agent, "reason": f"classifier:{agent}"}

    def agent(state: SellerState) -> dict:
        reply = bound[state["agent"]].invoke([SystemMessage(AGENTS[state["agent"]]), *state["messages"]])
        # Модель может попросить инструмент чужой роли — не исполняем ничего из этого ответа.
        # Отвечаем на каждый вызов, иначе история станет невалидной для API модели.
        allowed = set(AGENT_TOOLS[state["agent"]])
        if any(c["name"] not in allowed for c in reply.tool_calls):
            refusals = [
                ToolMessage(
                    f"Инструмент {c['name']} недоступен этой роли"
                    if c["name"] not in allowed
                    else "Не выполнено: в ответе был недоступный инструмент, повтори запрос",
                    tool_call_id=c["id"],
                )
                for c in reply.tool_calls
            ]
            return {"messages": [reply, *refusals]}
        return {"messages": [reply]}

    def after_agent(state: SellerState) -> str:
        last = state["messages"][-1]
        if isinstance(last, ToolMessage):  # отказ в чужом инструменте — пусть агент ответит иначе
            return "agent"
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(SellerState)
    graph.add_node("route", route)
    graph.add_node("classify", classify)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", lambda s: "agent" if s["agent"] else "classify", ["agent", "classify"])
    graph.add_edge("classify", "agent")
    graph.add_conditional_edges("agent", after_agent, ["tools", "agent", END])
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer)
