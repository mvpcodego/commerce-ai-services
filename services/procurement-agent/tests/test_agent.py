import json

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

from agent.data import load, reorder_plan
from agent.procurement_agent import DRAFT_TOOL, READ_TOOLS, build_options, build_server, human_approval, overshoot_guard


@pytest.fixture(scope="module")
def data():
    return load()


def handlers(data, drafts):
    import agent.procurement_agent as pa

    captured = {}
    original = pa.create_sdk_mcp_server
    pa.create_sdk_mcp_server = lambda name, tools: (
        captured.update({t.name: t.handler for t in tools}) or original(name, tools=tools)
    )
    try:
        build_server(data, drafts)
    finally:
        pa.create_sdk_mcp_server = original
    return captured


def payload(result):
    return json.loads(result["content"][0]["text"])


def test_plan_matches_dashboard_numbers(data):
    plan = reorder_plan(data)
    assert len(plan["to_order"]) == 16
    assert sum(r["amount"] for r in plan["to_order"]) == 548_140
    assert all(r["state"] != "idle" for r in plan["to_order"])  # «не продаётся» не закупаем


async def test_tools_answer_from_catalog(data, tmp_path):
    h = handlers(data, tmp_path)
    plan = payload(await h["get_reorder_plan"]({}))
    assert plan["to_order"][0]["sku"] == "HU-AURIO-S1-9"
    assert payload(await h["get_part"]({"sku": "нет-такого"}))["error"]


async def test_draft_is_written_with_catalog_prices(data, tmp_path):
    h = handlers(data, tmp_path)
    result = payload(await h["draft_purchase_request"]({"items": [{"sku": "HU-AURIO-S1-9", "quantity": 5}]}))
    draft = json.loads((tmp_path / result["file"]).read_text("utf-8"))
    assert draft["status"] == "draft" and draft["total"] == 131_500


@pytest.mark.parametrize(
    "items, denied",
    [
        ([{"sku": "HU-AURIO-S1-9", "quantity": 5}], False),  # ровно по расчёту
        ([{"sku": "HU-AURIO-S1-9", "quantity": 7}], False),  # 7 ≤ 5 × 1.5
        ([{"sku": "HU-AURIO-S1-9", "quantity": 8}], True),  # больше полутора расчётов
        ([{"sku": "CAM-001", "quantity": 1}], True),  # позиции нет в расчёте
    ],
)
async def test_overshoot_guard(data, items, denied):
    hook = overshoot_guard(data)
    out = await hook({"tool_name": DRAFT_TOOL, "tool_input": {"items": items}}, "t1", None)
    assert (out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny") is denied


async def test_guard_ignores_other_tools(data):
    assert await overshoot_guard(data)({"tool_name": READ_TOOLS[0], "tool_input": {}}, None, None) == {}


async def test_human_approval():
    asked = []

    async def say(answer):
        async def ask(question):
            asked.append(question)
            return answer

        return ask

    allow = human_approval(await say(True))
    deny = human_approval(await say(False))
    draft = {"items": [{"sku": "HU-AURIO-S1-9", "quantity": 5}]}

    assert isinstance(await allow(READ_TOOLS[0], {}, None), PermissionResultAllow)
    assert isinstance(await allow(DRAFT_TOOL, draft, None), PermissionResultAllow)
    assert isinstance(await deny(DRAFT_TOOL, draft, None), PermissionResultDeny)
    assert isinstance(await allow("Bash", {"command": "rm -rf /"}, None), PermissionResultDeny)
    assert asked == ["Записать черновик заявки: HU-AURIO-S1-9×5?"] * 2  # чтение и чужие инструменты не спрашивают


def test_options_lock_the_agent_down(data):
    async def never(_):
        return False

    options = build_options(data, never)
    assert options.tools == []  # ни файлов, ни терминала, ни веба
    assert options.allowed_tools == []  # каждое решение — в can_use_tool, ничего не разрешено мимо него
    assert options.max_budget_usd and options.max_turns
    assert options.setting_sources == []
