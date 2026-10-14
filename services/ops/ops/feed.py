"""Фид товаров для Яндекс.Маркета (формат YML).

Каталог раскладывается по типам товаров: каждая часть собирается отдельной задачей
Celery (group), а сборка файла ждёт всех (chord). Части не зависят друг от друга,
поэтому при росте каталога их можно раздать большему числу воркеров.
"""

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
from zoneinfo import ZoneInfo

from celery import chord
from sqlalchemy import Text, cast, create_engine, select

from ops import config
from ops.celery_app import app
from ops.models import parts

CATEGORIES = {
    "head_unit": (1, "Головные устройства"),
    "frame": (2, "Переходные рамки"),
    "wiring": (3, "Проводка"),
    "starter_kit": (4, "Стартовые наборы"),
    "camera": (5, "Камеры"),
    "adapter": (6, "Адаптеры"),
    "audio": (7, "Аудио"),
    "soundproofing": (8, "Шумоизоляция"),
    "door_closer": (9, "Доводчики дверей"),
    "alarm": (10, "Сигнализации"),
    "tuning": (11, "Тюнинг"),
    "accessory": (12, "Аксессуары"),
}
FEED_NAME = "yandex-market.yml"
_engine = None


def _db():
    # Celery-задачи синхронные: отдельный синхронный движок на тот же адрес и ту же роль.
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, pool_size=2, pool_pre_ping=True)
    return _engine


def offer_xml(part: dict, category_id: int) -> str:
    url = f"{config.SITE_URL}/shop/product/{part['sku']}"
    picture = part.get("image_url") or ""
    if picture.startswith("/"):
        picture = config.SITE_URL + picture
    lines = [
        f"<offer id={quoteattr(part['sku'])} available={quoteattr('true' if part['stock'] > 0 else 'false')}>",
        f"<url>{escape(url)}</url>",
        f"<price>{part['price_retail']}</price>",
        "<currencyId>RUR</currencyId>",
        f"<categoryId>{category_id}</categoryId>",
    ]
    if picture:
        lines.append(f"<picture>{escape(picture)}</picture>")
    lines.append(f"<name>{escape(part['title'])}</name>")
    if part.get("brand"):
        lines.append(f"<vendor>{escape(part['brand'])}</vendor>")
    lines += [f"<count>{max(part['stock'], 0)}</count>", "</offer>"]
    return "".join(lines)


@app.task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def build_part(part_type: str) -> dict:
    """Одна часть фида: предложения одного типа товаров."""
    # type в базе — enum part_type; сравнение через text, иначе Postgres не сравнит enum с varchar.
    category_id, _ = CATEGORIES[part_type]
    with _db().connect() as conn:
        rows = conn.execute(
            select(parts)
            .where(cast(parts.c.type, Text) == part_type, parts.c.archived.is_(False), parts.c.price_retail > 0)
            .order_by(parts.c.sku)
        ).mappings().all()
    return {"type": part_type, "count": len(rows), "xml": "\n".join(offer_xml(dict(r), category_id) for r in rows)}


@app.task
def assemble(chunks: list[dict], out_dir: str) -> dict:
    """Склеивает части в файл. Пишет во временный и переименовывает — файл никогда не бывает наполовину."""
    now = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%dT%H:%M%z")
    now = now[:-2] + ":" + now[-2:]
    categories = "\n".join(f'<category id="{cid}">{escape(name)}</category>' for cid, name in CATEGORIES.values())
    offers = "\n".join(c["xml"] for c in chunks if c["xml"])
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<yml_catalog date="{now}">\n<shop>\n<name>TMGoods</name>\n<company>TMGoods</company>\n'
        f"<url>{escape(config.SITE_URL)}</url>\n"
        '<currencies><currency id="RUR" rate="1"/></currencies>\n'
        f"<categories>\n{categories}\n</categories>\n<offers>\n{offers}\n</offers>\n</shop>\n</yml_catalog>\n"
    )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / (FEED_NAME + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(out / FEED_NAME)
    return {"file": str(out / FEED_NAME), "offers": sum(c["count"] for c in chunks), "parts": len(chunks), "bytes": len(body.encode())}


def start_feed(out_dir: str):
    """Ставит chord: части параллельно → сборка. Возвращает AsyncResult сборки."""
    return chord(build_part.s(t) for t in CATEGORIES)(assemble.s(out_dir))
