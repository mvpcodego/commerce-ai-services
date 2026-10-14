import json
from datetime import date, datetime

from sqlalchemy import text

from ops import config
from ops.tasks import TASKS


async def seed(sessions):
    async with sessions() as s:
        await s.execute(text("delete from public.kits; delete from public.parts"))
        await s.execute(text(
            "insert into public.parts values (1,'HU','ГУ','head_unit',1,1000,false,'Aurio','/parts/hu.svg'),(2,'FR','Рамка','frame',0,100,false,null,null),(3,'OLD','Старое','frame',9,50,true,null,null)"
        ))
        await s.execute(text("insert into public.kits values (7,1,2,null,null)"))
        for items, total, status, created in [
            ([{"sku": "kit-7", "quantity": 2}], 2200, "shipped", "2026-10-11T10:00:00+03:00"),
            ([{"sku": "FR", "quantity": 1}], 100, "new", "2026-10-11T23:30:00+03:00"),
            ([{"sku": "kit-7", "quantity": 1}], 1100, "cancelled", "2026-10-11T12:00:00+03:00"),
            ([{"sku": "HU", "quantity": 1}], 1000, "new", "2026-10-12T00:10:00+03:00"),  # уже следующие сутки
        ]:
            await s.execute(
                text("insert into public.site_orders (items, total, status, created_at) values (cast(:i as jsonb), :t, :s, :c)"),
                {"i": json.dumps(items), "t": total, "s": status, "c": datetime.fromisoformat(created)},
            )
        await s.commit()


async def test_procurement_task_reads_db(sessions):
    await seed(sessions)
    async with sessions() as s:
        r = await TASKS["procurement"](s, {"days": "9999", "lead": 0})
    assert r["params"] == {"days": 365, "lead": 1, "horizon": 30}
    assert r["orders"] == 4
    reorder = {row["sku"]: row["state"] for row in r["reorder"]}
    assert reorder == {"FR": "out"}  # ГУ: 1 шт. при 3 продажах за год — хватит на 121 день
    assert "OLD" not in reorder


async def test_export_orders_by_moscow_day(sessions, tmp_path, monkeypatch):
    await seed(sessions)
    monkeypatch.setattr(config, "EXPORT_DIR", tmp_path)
    async with sessions() as s:
        r = await TASKS["export_orders"](s, {"day": "2026-10-11"})
    assert r["orders"] == 3  # 00:10 12-го по Москве в 11-е не попадает
    lines = (tmp_path / "orders-2026-10-11.csv").read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("id;создан (МСК)")
    assert lines[2].split(";")[1] == "2026-10-11 23:30"


async def test_daily_summary_without_telegram(sessions, monkeypatch):
    await seed(sessions)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    async with sessions() as s:
        r = await TASKS["daily_summary"](s, {"day": date(2026, 10, 11).isoformat()})
    assert (r["orders"], r["revenue"], r["cancelled"], r["sent"]) == (2, 2300, 1, False)
    assert "Средний чек: 1 150 ₽" in r["text"]
