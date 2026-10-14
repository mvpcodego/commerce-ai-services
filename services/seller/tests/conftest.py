import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from seller.catalog import Catalog
from seller.graph import build_graph


class ScriptedModel(FakeMessagesListChatModel):
    """Модель-сценарий: отдаёт заготовленные ответы по очереди и запоминает, что ей прислали.

    Настоящей модели в тестах нет — проверяется граф: кто и сколько раз её вызывает,
    куда идут вызовы инструментов, где граф останавливается.
    """

    calls: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _get_ls_params(self, stop=None, **kwargs):
        # Настоящие модели сообщают своё имя так же — по нему трейсинг ищет цену.
        return {**super()._get_ls_params(stop=stop, **kwargs), "ls_model_name": "scripted"}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return super()._generate(messages, stop, run_manager, **kwargs)


@pytest.fixture
def catalog():
    return Catalog.load()


@pytest.fixture
def make_seller(catalog):
    def factory(*responses):
        model = ScriptedModel(responses=list(responses), calls=[])
        return build_graph(model, catalog, InMemorySaver()), model

    return factory
