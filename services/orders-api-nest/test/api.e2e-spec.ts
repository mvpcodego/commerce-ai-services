import type { INestApplication } from "@nestjs/common"
import { randomUUID } from "node:crypto"
import request from "supertest"
import type { App } from "supertest/types.js"
import { DataSource } from "typeorm"
import { InMemoryPublisher } from "../src/events/event-publisher.js"
import { OutboxRelay } from "../src/events/outbox.relay.js"
import { ADMIN_TOKEN, createTestApp, resetDatabase, testDatabaseReady } from "./helpers.js"

const dbReady = await testDatabaseReady()
if (!dbReady) console.warn("Postgres недоступен (docker compose up -d postgres) — e2e пропущены")
const describeDb = dbReady ? describe : describe.skip

const order = {
  customer: { name: "Роман Ершов", phone: "+7 900 000-00-00", city: "Казань" },
  items: [{ sku: "kit-47", quantity: 1 }, { sku: "HU-AURIO-S1-9", quantity: 2 }],
}

describeDb("API против Postgres", () => {
  let app: INestApplication
  let http: App
  let publisher: InMemoryPublisher
  const auth = { Authorization: `Bearer ${ADMIN_TOKEN}` }
  const post = (key: string | null, body: unknown) => {
    const r = request(http).post("/orders").send(body as object)
    return key ? r.set("Idempotency-Key", key) : r
  }

  beforeAll(async () => {
    await resetDatabase()
    publisher = new InMemoryPublisher()
    app = await createTestApp(publisher)
    http = app.getHttpServer() as App
  })

  afterAll(async () => {
    await app?.close()
  })

  describe("health и документация", () => {
    it("GET /health — база доступна", async () => {
      const res = await request(http).get("/health").expect(200)
      expect(res.body).toMatchObject({ status: "ok", db: "up", kafka: "disabled" })
    })

    it("GET /docs-json — описаны все маршруты", async () => {
      const res = await request(http).get("/docs-json").expect(200)
      expect(Object.keys(res.body.paths)).toEqual(
        expect.arrayContaining(["/orders", "/orders/{id}", "/orders/{id}/status", "/catalog/parts", "/catalog/kits/{sku}", "/health"]),
      )
    })

    it("CORS для админки на localhost:5173, заголовок повтора виден браузеру", async () => {
      const res = await request(http)
        .options("/orders")
        .set("Origin", "http://localhost:5173")
        .set("Access-Control-Request-Method", "PATCH")
        .set("Access-Control-Request-Headers", "authorization,idempotency-key,content-type")
      expect(res.headers["access-control-allow-origin"]).toBe("http://localhost:5173")
      const get = await request(http).get("/health").set("Origin", "http://localhost:5173")
      expect(get.headers["access-control-expose-headers"]).toContain("Idempotency-Replayed")
      const evil = await request(http).get("/health").set("Origin", "http://evil.example")
      expect(evil.headers["access-control-allow-origin"]).toBeUndefined()
    })
  })

  describe("каталог", () => {
    it("позиции: фильтр по типу и поиск, цены в копейках", async () => {
      const res = await request(http).get("/catalog/parts").query({ type: "head_unit", q: "aurio", limit: 5 }).expect(200)
      expect(res.body.total).toBeGreaterThan(0)
      for (const p of res.body.items) {
        expect(p.type).toBe("head_unit")
        expect(p.title.toLowerCase()).toContain("aurio")
        expect(Number.isInteger(p.priceKopecks)).toBe(true)
      }
    })

    it("комплект с составом и автомобилем", async () => {
      const res = await request(http).get("/catalog/kits/kit-47").expect(200)
      expect(res.body.kit).toMatchObject({ sku: "kit-47", priceKopecks: 3_550_000 })
      expect(res.body.car).toMatchObject({ make: "Hyundai", model: "Solaris" })
      expect(res.body.components.length).toBeGreaterThanOrEqual(3)
    })

    it("нет комплекта — 404 в общем формате; кривой фильтр — 400", async () => {
      const res = await request(http).get("/catalog/kits/kit-99999").expect(404)
      expect(res.body).toMatchObject({ statusCode: 404, code: "KIT_NOT_FOUND", path: "/catalog/kits/kit-99999" })
      const bad = await request(http).get("/catalog/parts").query({ type: "spaceship", limit: 0 }).expect(400)
      expect(bad.body.code).toBe("VALIDATION_FAILED")
    })
  })

  describe("создание заказа и идемпотентность", () => {
    it("201: цены из каталога, телефон нормализован, итог в копейках", async () => {
      const res = await post(randomUUID(), order).expect(201)
      expect(res.headers["idempotency-replayed"]).toBe("false")
      expect(res.body).toMatchObject({
        status: "new",
        customer: { name: "Роман Ершов", phone: "79000000000", city: "Казань" },
        totalKopecks: 3_550_000 + 2 * 2_630_000,
      })
    })

    it("повтор с тем же ключом — тот же ответ, заказ один", async () => {
      const key = randomUUID()
      const first = await post(key, order).expect(201)
      const again = await post(key, order).expect(201)
      expect(again.headers["idempotency-replayed"]).toBe("true")
      expect(again.body).toEqual(first.body)
      const count = await app.get(DataSource).query(`SELECT count(*)::int AS n FROM idempotency_keys k JOIN orders o ON o.id = k.order_id WHERE k.key = $1`, [key])
      expect(count[0].n).toBe(1)
    })

    it("повтор после смены статуса возвращает исходный ответ, а не текущее состояние", async () => {
      const key = randomUUID()
      const first = await post(key, order).expect(201)
      await request(http).patch(`/orders/${first.body.id}/status`).set(auth).send({ status: "confirmed" }).expect(200)
      const again = await post(key, order).expect(201)
      expect(again.body.status).toBe("new")
    })

    it("тот же ключ с другим телом — 409", async () => {
      const key = randomUUID()
      await post(key, order).expect(201)
      const res = await post(key, { ...order, items: [{ sku: "kit-47", quantity: 2 }] }).expect(409)
      expect(res.body.code).toBe("IDEMPOTENCY_KEY_REUSED")
    })

    it("10 параллельных запросов с одним ключом — один заказ", async () => {
      const key = randomUUID()
      const results = await Promise.all(Array.from({ length: 10 }, () => post(key, order)))
      expect(results.map((r) => r.status)).toEqual(Array(10).fill(201))
      expect(new Set(results.map((r) => r.body.id)).size).toBe(1)
      expect(results.filter((r) => r.headers["idempotency-replayed"] === "false")).toHaveLength(1)
    })

    it("без ключа — 400; кривое тело — 400 с полями", async () => {
      expect((await post(null, order).expect(400)).body.code).toBe("IDEMPOTENCY_KEY_REQUIRED")
      const res = await post(randomUUID(), { customer: { name: "R", phone: "1" }, items: [{ sku: "kit-47", quantity: 1, price: 1 }] }).expect(400)
      expect(res.body.code).toBe("VALIDATION_FAILED")
      expect(res.body.details.map((d: { field: string }) => d.field)).toEqual(
        expect.arrayContaining(["customer.name", "customer.phone", "items.0.price"]),
      )
    })

    it("неизвестный артикул — 422, ключ не сгорает: исправленный запрос с тем же ключом проходит", async () => {
      const key = randomUUID()
      const res = await post(key, { ...order, items: [{ sku: "NO-SUCH-SKU", quantity: 1 }] }).expect(422)
      expect(res.body).toMatchObject({ code: "UNKNOWN_SKU", details: { skus: ["NO-SUCH-SKU"] } })
      await post(key, order).expect(201)
    })
  })

  describe("outbox → публикация", () => {
    it("каждый новый заказ — одно событие order.created без ПДн; повтор не добавляет событие", async () => {
      const relay = app.get(OutboxRelay)
      await relay.runOnce() // выгрести накопленное предыдущими тестами
      publisher.sent.length = 0

      const key = randomUUID()
      const created = await post(key, order).expect(201)
      await post(key, order).expect(201)

      expect(await relay.runOnce()).toEqual({ published: 1, failed: 0 })
      expect(publisher.sent).toHaveLength(1)
      const [msg] = publisher.sent
      expect(msg).toMatchObject({ topic: "orders", key: String(created.body.id), headers: { "event-type": "order.created" } })
      const event = JSON.parse(msg.value)
      expect(event).toMatchObject({ type: "order.created", order_id: created.body.id, total_kopecks: created.body.totalKopecks })
      expect(event.occurred_at).toMatch(/Z$/)
      expect(msg.value).not.toContain("79000000000")
      expect(await relay.runOnce()).toEqual({ published: 0, failed: 0 })
    })

    it("брокер недоступен — событие остаётся, попытка и ошибка записаны, повтор с паузой", async () => {
      const relay = app.get(OutboxRelay)
      const db = app.get(DataSource)
      const created = await post(randomUUID(), order).expect(201)
      publisher.failNext = 1

      expect(await relay.runOnce()).toEqual({ published: 0, failed: 1 })
      const [row] = await db.query(
        `SELECT attempts, last_error, published_at, available_at > now() AS delayed FROM outbox WHERE message_key = $1`,
        [String(created.body.id)],
      )
      expect(row).toMatchObject({ attempts: 1, last_error: "брокер недоступен (тест)", published_at: null, delayed: true })

      // Пауза ещё идёт — релей событие не трогает; после паузы отправляет.
      expect(await relay.runOnce()).toEqual({ published: 0, failed: 0 })
      await db.query(`UPDATE outbox SET available_at = now() WHERE message_key = $1`, [String(created.body.id)])
      expect(await relay.runOnce()).toEqual({ published: 1, failed: 0 })
    })
  })

  describe("админка: список, карточка, статусы", () => {
    it("без токена — 401, с чужим — 401", async () => {
      expect((await request(http).get("/orders").expect(401)).body.code).toBe("UNAUTHORIZED")
      await request(http).get("/orders/1").set("Authorization", "Bearer nope").expect(401)
      await request(http).patch("/orders/1/status").send({ status: "confirmed" }).expect(401)
    })

    it("список: новые сверху, пагинация, фильтр по статусу", async () => {
      const all = await request(http).get("/orders").set(auth).query({ limit: 3 }).expect(200)
      expect(all.body).toMatchObject({ page: 1, limit: 3 })
      expect(all.body.items).toHaveLength(3)
      const ids = all.body.items.map((o: { id: number }) => o.id)
      expect(ids).toEqual([...ids].sort((a, b) => b - a))

      const page2 = await request(http).get("/orders").set(auth).query({ limit: 3, page: 2 }).expect(200)
      expect(page2.body.items[0].id).toBeLessThan(ids[2])

      const confirmed = await request(http).get("/orders").set(auth).query({ status: "confirmed" }).expect(200)
      expect(confirmed.body.total).toBeGreaterThan(0)
      expect(confirmed.body.items.every((o: { status: string }) => o.status === "confirmed")).toBe(true)
    })

    it("путь new → confirmed → shipped → delivered; дальше и назад — 409", async () => {
      const { body } = await post(randomUUID(), order).expect(201)
      const patch = (status: string) => request(http).patch(`/orders/${body.id}/status`).set(auth).send({ status })

      expect((await patch("confirmed").expect(200)).body.allowedTransitions).toEqual(["shipped", "cancelled"])
      await patch("shipped").expect(200)
      const cancel = await patch("cancelled").expect(409)
      expect(cancel.body).toMatchObject({ code: "INVALID_TRANSITION", details: { from: "shipped", allowed: ["delivered"] } })
      expect((await patch("delivered").expect(200)).body.allowedTransitions).toEqual([])

      const card = await request(http).get(`/orders/${body.id}`).set(auth).expect(200)
      expect(card.body.status).toBe("delivered")
    })

    it("две админки одновременно подтверждают один заказ — проходит ровно одна (блокировка строки)", async () => {
      const { body } = await post(randomUUID(), order).expect(201)
      const results = await Promise.all(
        [1, 2].map(() => request(http).patch(`/orders/${body.id}/status`).set(auth).send({ status: "confirmed" })),
      )
      expect(results.map((r) => r.status).sort()).toEqual([200, 409])
    })

    it("нет заказа — 404, id не число — 400, неизвестный статус — 400", async () => {
      expect((await request(http).get("/orders/999999").set(auth).expect(404)).body.code).toBe("ORDER_NOT_FOUND")
      await request(http).get("/orders/abc").set(auth).expect(400)
      const bad = await request(http).patch("/orders/1/status").set(auth).send({ status: "lost" }).expect(400)
      expect(bad.body.code).toBe("VALIDATION_FAILED")
    })
  })
})
