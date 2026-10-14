"""Шлюз моделей на LiteLLM: роли графа обращаются к псевдонимам, а не к провайдерам.

    seller-fast   классификатор, приветствие, возражения, допродажа
    seller-smart  подбор комплекта и оформление заказа; упал — запрос уходит на seller-fast

Какая модель стоит за псевдонимом, задаётся переменными окружения — граф и промпты при смене
провайдера не меняются. Расход каждого вызова пишется в журнал (CostLedger) по псевдониму
и фактической модели: видно, сколько стоит каждая роль и как часто срабатывает запасной вариант.
"""

import os
from collections import defaultdict
from typing import Any

import litellm
from langchain_litellm import ChatLiteLLMRouter
from litellm import Router
from litellm.integrations.custom_logger import CustomLogger

FAST, SMART = "seller-fast", "seller-smart"
ROLE_TIER = {
    "classifier": FAST,
    "greeter": FAST,
    "objection_handler": FAST,
    "upsell": FAST,
    "product_finder": SMART,
    "order_agent": SMART,
}


def default_model_list() -> list[dict[str, Any]]:
    """Модели из окружения: SELLER_FAST_MODEL / SELLER_SMART_MODEL в формате LiteLLM (провайдер/модель)."""
    return [
        {
            "model_name": FAST,
            "litellm_params": {"model": os.environ.get("SELLER_FAST_MODEL", "anthropic/claude-haiku-4-5")},
        },
        {
            "model_name": SMART,
            "litellm_params": {"model": os.environ.get("SELLER_SMART_MODEL", "anthropic/claude-sonnet-5-5")},
        },
    ]


class CostLedger(CustomLogger):
    """Журнал расходов: псевдоним → вызовы, токены, деньги. Плюс счётчик срабатываний запасной модели."""

    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self) -> None:
        self.by_alias: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
        self.models: dict[str, int] = defaultdict(int)
        self.failures: dict[str, int] = defaultdict(int)

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        alias = (kwargs.get("litellm_params") or {}).get("metadata", {}).get("model_group") or kwargs.get("model")
        row = self.by_alias[alias]
        row["calls"] += 1
        row["tokens"] += getattr(getattr(response_obj, "usage", None), "total_tokens", 0) or 0
        row["cost"] += kwargs.get("response_cost") or 0.0
        self.models[kwargs.get("model", "?")] += 1

    def log_failure_event(self, kwargs, response_obj, start_time, end_time):
        alias = (kwargs.get("litellm_params") or {}).get("metadata", {}).get("model_group") or kwargs.get("model")
        self.failures[alias] += 1

    async def async_log_success_event(self, *args):
        self.log_success_event(*args)

    async def async_log_failure_event(self, *args):
        self.log_failure_event(*args)

    @property
    def total_cost(self) -> float:
        return sum(row["cost"] for row in self.by_alias.values())


def make_router(model_list: list[dict[str, Any]] | None = None, ledger: CostLedger | None = None) -> Router:
    if ledger is not None and ledger not in litellm.callbacks:
        litellm.callbacks.append(ledger)
    return Router(
        model_list=model_list or default_model_list(),
        fallbacks=[{SMART: [FAST]}],
        num_retries=1,
        timeout=60,
    )


def role_models(router: Router) -> dict[str, ChatLiteLLMRouter]:
    """Модель для каждой роли графа — передаётся в build_graph(role_models=...)."""
    return {role: ChatLiteLLMRouter(router=router, model_name=tier) for role, tier in ROLE_TIER.items()}
