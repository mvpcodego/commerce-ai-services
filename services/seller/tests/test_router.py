"""Регрессия правил: живые фразы покупателей и куда они должны уйти."""

import pytest

from seller.router import route_message

AFTER_PRODUCTS = [("user", "kia rio"), ("assistant", "Под Kia Rio есть комплект: Aurio S3 + рамка")]


@pytest.mark.parametrize(
    "message, history, agent",
    [
        ("привет", [], "greeter"),
        ("Привет, подскажите", [], "greeter"),  # кириллица на границе слова — грабля TS-версии
        ("добрый день", [], "greeter"),
        ("kia sportage 2019", [], "product_finder"),
        ("лада веста", [], "product_finder"),
        ("рамка на весту", [], "product_finder"),
        ("камера заднего вида", [], "product_finder"),
        ("kia", [], "greeter"),
        ("беру, оформляем", [], "order_agent"),
        ("дорого", AFTER_PRODUCTS, "objection_handler"),
        ("дорого, есть подешевле?", AFTER_PRODUCTS, "product_finder"),
        ("а камеру добавить?", AFTER_PRODUCTS, "upsell"),
        ("что у вас есть?", [], "greeter"),
    ],
)
def test_route(message, history, agent):
    assert route_message(message, history).agent == agent


def test_question_about_ordering_is_not_an_order():
    # «как заказать?» — вопрос, а не готовность купить: иначе человек получит требование телефона.
    assert route_message("как заказать?", []).agent != "order_agent"


def test_ambiguous_goes_to_classifier():
    for message in ("дорого", "ну такое"):
        route = route_message(message, [])
        assert route.agent is None and route.confidence == "low"


def test_every_decision_has_a_reason():
    for message in ("привет", "kia rio", "беру", "дорого", "ну такое"):
        assert route_message(message, AFTER_PRODUCTS).reason
