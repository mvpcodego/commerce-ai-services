"""Маршрутизация сообщения покупателя правилами, без вызова модели.

Порт lib/ai/agents/router.ts. Важная разница: в JavaScript `\\b` не видит кириллицу,
и в TS-версии границы слов пришлось собирать из юникодных классов. В Python `re`
со строками str юникодный по умолчанию, `\\b` работает с русскими словами как есть.
"""

import re
from dataclasses import dataclass
from typing import Literal

AgentType = Literal["greeter", "product_finder", "objection_handler", "order_agent", "upsell"]
AGENTS: tuple[AgentType, ...] = ("greeter", "product_finder", "objection_handler", "order_agent", "upsell")


def _words(source: str) -> re.Pattern:
    return re.compile(rf"\b(?:{source})\b", re.IGNORECASE)


CAR_BRANDS = _words(
    r"лада|lada|веста|vesta|гранта|granta|калина|kalina|приора|priora|нива|niva|kia|киа|rio|рио|sportage|спортейдж|"
    r"sorento|соренто|ceed|сид|hyundai|хёндай|хюндай|хундай|solaris|соларис|creta|крета|elantra|элантра|tucson|туксон|"
    r"santa\s*fe|ix35|i30|toyota|тойота|camry|камри|rav4|рав4|corolla|королла|highlander|хайлендер|land\s*cruiser|"
    r"prado|прадо|honda|хонда|crv|cr-v|hrv|hr-v|mazda|мазда|cx5|cx-5|cx3|cx-3|nissan|ниссан|qashqai|кашкай|x-trail|"
    r"xtrail|tiida|тиида|mitsubishi|мицубиси|outlander|аутлендер|lancer|лансер|pajero|паджеро|ford|форд|focus|фокус|"
    r"mondeo|мондео|kuga|куга|mustang|мустанг|volkswagen|фольксваген|vw|polo|поло|jetta|джетта|tiguan|тигуан|passat|"
    r"пассат|golf|гольф|bmw|бмв|mercedes|мерседес|audi|ауди|skoda|шкода|octavia|октавия|rapid|рапид|kodiaq|кодиак|"
    r"renault|рено|logan|логан|duster|дастер|kaptur|каптур|sandero|сандеро|peugeot|пежо|chevrolet|шевроле|opel|опель|"
    r"subaru|субару|suzuki|сузуки|vitara|витара|lexus|лексус|infiniti|инфинити|chery|чери|haval|хавал|geely|джили|"
    r"changan|чанган|omoda|exeed|jetour|byd|tank|танк|jaecoo|jac|джак|great\s*wall|грейтвол"
)
CAR_MODEL = re.compile(r"(?:для|на|в|под)\s+[A-ZА-ЯЁa-zа-яё]{2,}\s+[A-ZА-ЯЁa-zа-яё0-9]{2,}", re.IGNORECASE)
SPECIFIC_PRODUCT = _words(
    r"камер[аыу]|регистратор\w*|микрофон\w*|шумоизоляц\w*|звукоизоляц\w*|доводчик\w*|сигнализац\w*|антенн\w*|"
    r"переходник\w*|усилител\w*|сабвуфер\w*|динамик\w*|колонк\w*|акустик\w*"
)
PRODUCT_FOR_CAR = re.compile(r"\b(?:рамк[аыу]|проводк[аыу]|камер[аыу]|доводчик)\b.*\b(?:на|для|под)\b", re.IGNORECASE)
OBJECTION = _words(
    r"дорого|дешевле|дешевое|конкурент\w*|подумаю|подумать|посоветуюсь|не уверен|сомневаюсь|завышен\w*|"
    r"переплат\w*|слишком дорог\w*|не стоит того|передумал|дороговат\w*|много денег"
)
CHEAPER = re.compile(r"дешевле|подешевле|бюджетн|попроще|проще", re.IGNORECASE)
ORDER = _words(
    r"оформи|оформить|заказать|купить|покупаю|беру|оплат\w*|оформляем|закажу|куплю|возьму|оформляй|давай оформим"
)
ORDER_QUESTION = _words(r"как|где|куда|можно ли|можно|а можно|сколько стоит доставк\w*|как оплатить|как получить")
UPSELL = _words(
    r"а ещё|а еще|добавить|добавь|дополнительно|допы|что ещё|что еще|камеру тоже|регистратор тоже|и камеру|"
    r"и шумку|плюс|вместе с"
)
GREETING = re.compile(
    r"^(?:привет|здравствуй\w*|добрый|здрасте|хай|хей|hello|hi|hey|приветик|приветствую|доброе утро|"
    r"добрый день|добрый вечер|ку|салам|йо)\b",
    re.IGNORECASE,
)
GENERAL = _words(
    r"что у вас|что есть|каталог|ассортимент|что посоветуете|что можете|покажите|расскажите|подскажите что|"
    r"что предлагаете|что продаёте|что продаете"
)
BRAND_ONLY = re.compile(r"^[а-яёa-z\s]{2,15}$", re.IGNORECASE)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


@dataclass(frozen=True)
class Route:
    agent: AgentType | None
    confidence: Literal["high", "medium", "low"]
    reason: str


def route_message(message: str, history: list[tuple[str, str]]) -> Route:
    """history — пары (role, content), role: "user" или "assistant"."""
    msg = message.strip()
    last_assistant = next((c for r, c in reversed(history) if r == "assistant"), "")

    if ORDER.search(msg) and not ORDER_QUESTION.search(msg):
        return Route("order_agent", "high", "order_keywords")

    if OBJECTION.search(msg):
        if "[product:" in last_assistant or "комплект" in last_assistant or len(history) > 2:
            if CHEAPER.search(msg):
                return Route("product_finder", "medium", "objection_with_alternative")
            return Route("objection_handler", "high", "objection_after_product")
        return Route(None, "low", "objection_no_context")

    if UPSELL.search(msg) and history:
        return Route("upsell", "high", "upsell_keywords")

    if PRODUCT_FOR_CAR.search(msg):
        return Route("product_finder", "high", "product_for_car")

    if CAR_BRANDS.search(msg):
        if YEAR.search(msg) or CAR_MODEL.search(msg) or len(msg.split()) >= 2:
            return Route("product_finder", "high", "car_brand_model")
        if SPECIFIC_PRODUCT.search(msg):
            return Route("product_finder", "high", "product_with_brand")
        return Route("greeter", "high", "brand_only_needs_model")

    if SPECIFIC_PRODUCT.search(msg):
        return Route("product_finder", "high", "specific_product")

    if GREETING.search(msg):
        return Route("greeter", "high", "greeting")

    if GENERAL.search(msg):
        return Route("greeter", "medium", "general_question")

    if BRAND_ONLY.search(msg) and CAR_BRANDS.search(msg):
        return Route("greeter", "medium", "brand_only_short")

    if history:
        if "[product:" in last_assistant or "комплект" in last_assistant:
            return Route("product_finder", "low", "followup_after_products")
        if re.search(r"заказ|оформлен|имя|телефон", last_assistant):
            return Route("order_agent", "medium", "followup_after_order")

    return Route(None, "low", "ambiguous")
