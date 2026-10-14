"""Агент закупок на Claude Agent SDK.

Сам считает потребность (инструмент поверх расчёта ops), сверяет позиции и готовит черновик
заявки поставщику. Записать черновик может только после разрешения человека, а два
предохранителя работают в коде, независимо от модели:

- PreToolUse-хук отклоняет заявку, где количество по позиции больше рекомендованного
  расчётом в 1.5 раза или позиции нет в расчёте — модель получает причину и правит заявку;
- can_use_tool спрашивает человека перед записью; без ответа «да» черновик не пишется.

Встроенных инструментов Claude Code (файлы, терминал, веб) у агента нет: tools=[],
только свой MCP-сервер в процессе. Ход ограничен max_turns и бюджетом max_budget_usd.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from agent.data import load, reorder_plan

SERVER = "procurement"
READ_TOOLS = [f"mcp__{SERVER}__get_reorder_plan", f"mcp__{SERVER}__get_part"]
DRAFT_TOOL = f"mcp__{SERVER}__draft_purchase_request"
MAX_OVERSHOOT = 1.5
DRAFTS = Path(__file__).resolve().parents[1] / "drafts"

SYSTEM_PROMPT = """Ты — агент закупок магазина автомагнитол. Подготовь черновик заявки поставщику.
Порядок: get_reorder_plan → проверь спорные позиции через get_part → draft_purchase_request.
Параметры расчёта не спрашивай — бери значения по умолчанию. Бери количества из расчёта; отклоняться можно только с объяснением в comment.
Позиции «Не продаётся» в заявку не включай. Ответ — коротко: сколько позиций, на какую сумму, что исключено и почему."""


def _text(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def build_server(data: dict, drafts: Path = DRAFTS):
    parts = {p["sku"]: p for p in data["parts"]}

    @tool(
        "get_reorder_plan",
        "Расчёт закупки: что заканчивается и сколько заказать. Параметры необязательны.",
        {
            "type": "object",
            "properties": {
                "lead_days": {"type": "integer", "description": "Срок поставки, дней. По умолчанию 14"},
                "horizon_days": {"type": "integer", "description": "Горизонт запаса, дней. По умолчанию 30"},
            },
        },
    )
    async def get_reorder_plan(args: dict[str, Any]) -> dict[str, Any]:
        return _text(reorder_plan(data, lead=args.get("lead_days", 14), horizon=args.get("horizon_days", 30)))

    @tool("get_part", "Позиция каталога по артикулу: цена, остаток, тип", {"sku": str})
    async def get_part(args: dict[str, Any]) -> dict[str, Any]:
        part = parts.get(args["sku"])
        return _text(part or {"error": f"Позиции {args['sku']} нет в каталоге"})

    @tool(
        "draft_purchase_request",
        "Записать черновик заявки поставщику. Требует подтверждения человека.",
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"sku": {"type": "string"}, "quantity": {"type": "integer"}},
                        "required": ["sku", "quantity"],
                    },
                },
                "comment": {"type": "string"},
            },
            "required": ["items"],
        },
    )
    async def draft_purchase_request(args: dict[str, Any]) -> dict[str, Any]:
        lines = [
            {
                "sku": i["sku"],
                "title": parts[i["sku"]]["title"],
                "quantity": i["quantity"],
                "amount": i["quantity"] * (parts[i["sku"]].get("price_retail") or 0),
            }
            for i in args["items"]
        ]
        draft = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "draft",
            "items": lines,
            "total": sum(line["amount"] for line in lines),
            "comment": args.get("comment", ""),
        }
        drafts.mkdir(exist_ok=True)
        path = drafts / f"request-{datetime.now():%Y%m%d-%H%M%S}.json"
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), "utf-8")
        return _text({"ok": True, "file": path.name, "positions": len(lines), "total": draft["total"]})

    return create_sdk_mcp_server(SERVER, tools=[get_reorder_plan, get_part, draft_purchase_request])


def overshoot_guard(data: dict) -> Callable[..., Awaitable[dict[str, Any]]]:
    """PreToolUse: заявка не может разойтись с расчётом больше чем в MAX_OVERSHOOT раз."""
    recommended = {r["sku"]: r["reorder"] for r in reorder_plan(data)["to_order"]}

    async def hook(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        if input_data.get("tool_name") != DRAFT_TOOL:
            return {}
        problems = []
        for item in input_data.get("tool_input", {}).get("items", []):
            limit = recommended.get(item["sku"])
            if limit is None:
                problems.append(f"{item['sku']}: нет в расчёте закупки")
            elif item["quantity"] > limit * MAX_OVERSHOOT:
                problems.append(f"{item['sku']}: {item['quantity']} шт. при рекомендованных {limit}")
        if not problems:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Заявка расходится с расчётом: " + "; ".join(problems),
            }
        }

    return hook


def human_approval(ask: Callable[[str], Awaitable[bool]]):
    """can_use_tool: черновик пишется только после «да» человека, остальное агенту закрыто."""

    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any):
        if tool_name in READ_TOOLS:
            return PermissionResultAllow()
        if tool_name == DRAFT_TOOL:
            items = ", ".join(f"{i['sku']}×{i['quantity']}" for i in tool_input.get("items", []))
            if await ask(f"Записать черновик заявки: {items}?"):
                return PermissionResultAllow()
            return PermissionResultDeny(message="Человек не подтвердил заявку. Спроси, что поправить.")
        return PermissionResultDeny(message=f"Инструмент {tool_name} агенту закупок недоступен")

    return can_use_tool


def build_options(data: dict, ask: Callable[[str], Awaitable[bool]], model: str | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        tools=[],  # без встроенных инструментов Claude Code
        mcp_servers={SERVER: build_server(data)},
        # allowed_tools пуст сознательно: разрешённый там инструмент проходит мимо can_use_tool,
        # а решение по каждому вызову должно приниматься в одном месте — в human_approval.
        can_use_tool=human_approval(ask),
        hooks={"PreToolUse": [HookMatcher(matcher=DRAFT_TOOL, hooks=[overshoot_guard(data)])]},
        max_turns=10,
        max_budget_usd=0.5,
        model=model,
        setting_sources=[],  # не подхватывать настройки и правила пользователя
    )


async def ask_in_terminal(question: str) -> bool:
    answer = await asyncio.to_thread(input, f"{question} [да/нет] ")
    return answer.strip().lower() in {"да", "д", "yes", "y"}


async def main(model: str | None = None) -> None:
    data = load()

    async def prompt():  # can_use_tool требует потокового ввода
        yield {"type": "user", "message": {"role": "user", "content": "Подготовь заявку на закупку."}}

    async for message in query(prompt=prompt(), options=build_options(data, ask_in_terminal, model)):
        if isinstance(message, ResultMessage):
            print(message.result)
            print(f"ходов: {message.num_turns}, стоимость: ${message.total_cost_usd or 0:.4f}")


if __name__ == "__main__":
    import sys

    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
