import { jest } from "@jest/globals"
import type { DataSource } from "typeorm"
import type { CatalogService, Sellable } from "../catalog/catalog.service.js"
import { DomainError } from "../common/domain-error.js"
import type { CreateOrderDto, OrderView } from "./dto/order.dto.js"
import { requestHash } from "./idempotency.js"
import { IdempotencyKey, Order, OrderItem, OutboxEvent } from "./orders.entities.js"
import { OrdersService } from "./orders.service.js"

/** Менеджер в памяти: ровно те вызовы, что делает сервис. Поведение Postgres проверяют e2e. */
class FakeManager {
  keys = new Map<string, IdempotencyKey>()
  orders: Order[] = []
  items: OrderItem[] = []
  outbox: OutboxEvent[] = []

  query = jest.fn(async (_sql: string, [key, hash]: [string, string]) => {
    if (this.keys.has(key)) return []
    this.keys.set(key, Object.assign(new IdempotencyKey(), { key, requestHash: hash, orderId: null, response: null }))
    return [{ key }]
  })

  create<T>(cls: new () => T, data: Partial<T>): T {
    return Object.assign(new cls() as object, data) as T
  }

  async save<T>(entity: T | T[]): Promise<T | T[]> {
    const save = (e: unknown) => {
      if (e instanceof Order) {
        if (!e.id) Object.assign(e, { id: this.orders.length + 1, createdAt: new Date("2026-10-19T10:00:00Z") })
        e.updatedAt = new Date("2026-10-19T10:00:00Z")
        if (!this.orders.includes(e)) this.orders.push(e)
      } else if (e instanceof OrderItem) this.items.push(e)
      else if (e instanceof OutboxEvent) this.outbox.push(e)
      return e
    }
    return Array.isArray(entity) ? entity.map(save) as T[] : save(entity) as T
  }

  async update(_cls: unknown, { key }: { key: string }, patch: Partial<IdempotencyKey>) {
    Object.assign(this.keys.get(key)!, patch)
  }

  async findOneByOrFail(_cls: unknown, { key }: { key: string }) {
    return this.keys.get(key)!
  }

  async findOneBy(_cls: unknown, { id }: { id: number }) {
    return this.orders.find((o) => o.id === id) ?? null
  }

  async findOne(_cls: unknown, { where: { id } }: { where: { id: number } }) {
    return this.orders.find((o) => o.id === id) ?? null
  }

  async findBy(_cls: unknown, { orderId }: { orderId: number }) {
    return this.items.filter((i) => i.orderId === orderId)
  }
}

const sellable: Sellable[] = [
  { sku: "kit-47", title: "Hyundai Solaris + Nordvox N2 9\"", priceKopecks: 3_550_000 },
  { sku: "CAM-1", title: "Камера", priceKopecks: 199_990 },
]

function setup() {
  const m = new FakeManager()
  const ds = { transaction: (cb: (manager: FakeManager) => unknown) => cb(m), manager: m } as unknown as DataSource
  const resolveSellable = jest.fn(async (skus: string[]) => new Map(sellable.filter((s) => skus.includes(s.sku)).map((s) => [s.sku, s])))
  const service = new OrdersService(ds, { resolveSellable } as unknown as CatalogService)
  return { m, service, resolveSellable }
}

const dto: CreateOrderDto = {
  customer: { name: "Роман Ершов", phone: "79000000000", city: "Казань" },
  items: [{ sku: "kit-47", quantity: 1 }, { sku: "CAM-1", quantity: 2 }],
}

describe("OrdersService.create", () => {
  it("новый ключ: заказ по ценам каталога, строки, ответ сохранён при ключе, событие в outbox без ПДн", async () => {
    const { m, service } = setup()
    const { order, replayed } = await service.create("key-00000001", dto)

    expect(replayed).toBe(false)
    expect(order).toMatchObject({ id: 1, status: "new", totalKopecks: 3_949_980, allowedTransitions: ["confirmed", "cancelled"] })
    expect(order.items.map((i) => i.lineTotalKopecks)).toEqual([3_550_000, 399_980])
    expect(m.keys.get("key-00000001")).toMatchObject({ requestHash: requestHash(dto), orderId: 1, response: order })

    expect(m.outbox).toHaveLength(1)
    const event = m.outbox[0]
    expect(event).toMatchObject({ topic: "orders", messageKey: "1", attempts: 0 })
    expect(event.payload).toMatchObject({ type: "order.created", order_id: 1, total_kopecks: 3_949_980, items: [{ sku: "kit-47", quantity: 1 }, { sku: "CAM-1", quantity: 2 }] })
    expect(JSON.stringify(event.payload)).not.toMatch(/79000000000|Ершов/)
  })

  it("повтор с тем же ключом и телом — тот же ответ, второго заказа и события нет", async () => {
    const { m, service, resolveSellable } = setup()
    const first = await service.create("key-00000001", dto)
    const second = await service.create("key-00000001", { ...dto, customer: { ...dto.customer } })

    expect(second.replayed).toBe(true)
    expect(second.order).toEqual(first.order)
    expect(m.orders).toHaveLength(1)
    expect(m.outbox).toHaveLength(1)
    expect(resolveSellable).toHaveBeenCalledTimes(1)
  })

  it("тот же ключ с другим телом — 409 IDEMPOTENCY_KEY_REUSED", async () => {
    const { m, service } = setup()
    await service.create("key-00000001", dto)
    await expect(service.create("key-00000001", { ...dto, items: [{ sku: "kit-47", quantity: 3 }] })).rejects.toMatchObject({
      status: 409,
      code: "IDEMPOTENCY_KEY_REUSED",
    })
    expect(m.orders).toHaveLength(1)
  })

  it("неизвестный артикул — 422, заказ не создан", async () => {
    const { m, service } = setup()
    await expect(service.create("key-00000002", { ...dto, items: [{ sku: "NOPE", quantity: 1 }] })).rejects.toMatchObject({ status: 422, code: "UNKNOWN_SKU" })
    expect(m.orders).toHaveLength(0)
    expect(m.outbox).toHaveLength(0)
  })
})

describe("OrdersService.changeStatus", () => {
  async function withOrder() {
    const s = setup()
    const { order } = await s.service.create("key-00000001", dto)
    return { ...s, id: order.id }
  }

  it("разрешённый переход сохраняется, в ответе новые allowedTransitions", async () => {
    const { service, id } = await withOrder()
    const view: OrderView = await service.changeStatus(id, { status: "confirmed" })
    expect(view.status).toBe("confirmed")
    expect(view.allowedTransitions).toEqual(["shipped", "cancelled"])
  })

  it("запрещённый переход — 409 с разрешёнными вариантами, статус не меняется", async () => {
    const { m, service, id } = await withOrder()
    const error = await service.changeStatus(id, { status: "delivered" }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(DomainError)
    expect(error).toMatchObject({ status: 409, code: "INVALID_TRANSITION", details: { from: "new", to: "delivered", allowed: ["confirmed", "cancelled"] } })
    expect(m.orders[0].status).toBe("new")
  })

  it("нет заказа — 404", async () => {
    const { service } = setup()
    await expect(service.changeStatus(999, { status: "confirmed" })).rejects.toMatchObject({ status: 404, code: "ORDER_NOT_FOUND" })
  })
})
