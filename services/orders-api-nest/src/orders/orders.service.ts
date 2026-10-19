import { Injectable } from "@nestjs/common"
import { InjectDataSource } from "@nestjs/typeorm"
import { randomUUID } from "node:crypto"
import { DataSource, EntityManager, In } from "typeorm"
import { CatalogService } from "../catalog/catalog.service.js"
import { DomainError } from "../common/domain-error.js"
import { ORDERS_TOPIC, type OrderCreatedEvent } from "../events/order-events.js"
import type { ChangeStatusDto, CreateOrderDto, ListOrdersQuery, OrderPage, OrderView } from "./dto/order.dto.js"
import { assertSameRequest, requestHash } from "./idempotency.js"
import { canTransition, TRANSITIONS } from "./order-status.js"
import { IdempotencyKey, Order, OrderItem, OutboxEvent } from "./orders.entities.js"
import { priceOrder } from "./pricing.js"

export function toView(order: Order, items: OrderItem[]): OrderView {
  return {
    id: order.id,
    status: order.status,
    allowedTransitions: [...TRANSITIONS[order.status]],
    customer: { name: order.customerName, phone: order.customerPhone, city: order.customerCity },
    items: items
      .sort((a, b) => a.position - b.position)
      .map((i) => ({ sku: i.sku, title: i.title, unitPriceKopecks: i.unitPriceKopecks, quantity: i.quantity, lineTotalKopecks: i.lineTotalKopecks })),
    totalKopecks: order.totalKopecks,
    createdAt: order.createdAt.toISOString(),
    updatedAt: order.updatedAt.toISOString(),
  }
}

@Injectable()
export class OrdersService {
  constructor(
    @InjectDataSource() private readonly ds: DataSource,
    private readonly catalog: CatalogService,
  ) {}

  /**
   * Создание с ключом идемпотентности. Всё в одной транзакции: ключ, заказ, строки, событие в outbox.
   * Параллельный запрос с тем же ключом ждёт на INSERT ... ON CONFLICT, пока первый не закоммитится,
   * и получает сохранённый ответ. Ошибка (422, сбой) откатывает и ключ — его можно отправить снова.
   */
  async create(key: string, dto: CreateOrderDto): Promise<{ order: OrderView; replayed: boolean }> {
    const hash = requestHash(dto)
    return this.ds.transaction(async (m) => {
      const claimed = await m.query<unknown[]>(
        `INSERT INTO idempotency_keys (key, request_hash) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING RETURNING key`,
        [key, hash],
      )
      if (claimed.length === 0) {
        const existing = await m.findOneByOrFail(IdempotencyKey, { key })
        assertSameRequest(existing.requestHash, hash)
        return { order: existing.response as OrderView, replayed: true }
      }

      const catalog = await this.catalog.resolveSellable(dto.items.map((i) => i.sku), m)
      const { lines, totalKopecks } = priceOrder(dto.items, catalog)

      const order = await m.save(
        m.create(Order, {
          status: "new",
          customerName: dto.customer.name,
          customerPhone: dto.customer.phone,
          customerCity: dto.customer.city ?? null,
          totalKopecks,
        }),
      )
      const items = await m.save(lines.map((l) => m.create(OrderItem, { ...l, orderId: order.id })))
      const view = toView(order, items)

      await m.update(IdempotencyKey, { key }, { orderId: order.id, response: view })
      await m.save(m.create(OutboxEvent, this.orderCreatedOutbox(view)))
      return { order: view, replayed: false }
    })
  }

  private orderCreatedOutbox(order: OrderView): Partial<OutboxEvent> {
    const event: OrderCreatedEvent = {
      event_id: randomUUID(),
      type: "order.created",
      occurred_at: order.createdAt,
      order_id: order.id,
      // Без имени и телефона: потребителям (ops) нужен состав, а не покупатель.
      items: order.items.map(({ sku, quantity }) => ({ sku, quantity })),
      total_kopecks: order.totalKopecks,
    }
    return {
      eventId: event.event_id,
      topic: ORDERS_TOPIC,
      messageKey: String(order.id),
      payload: event,
      availableAt: new Date(),
      attempts: 0,
    }
  }

  async get(id: number, m: EntityManager = this.ds.manager): Promise<OrderView> {
    const order = await m.findOneBy(Order, { id })
    if (!order) throw new DomainError(404, "ORDER_NOT_FOUND", `Заказ ${id} не найден`)
    return toView(order, await m.findBy(OrderItem, { orderId: id }))
  }

  async list(query: ListOrdersQuery): Promise<OrderPage> {
    const [orders, total] = await this.ds.getRepository(Order).findAndCount({
      where: query.status ? { status: query.status } : {},
      order: { createdAt: "DESC", id: "DESC" },
      skip: (query.page - 1) * query.limit,
      take: query.limit,
    })
    const items = orders.length ? await this.ds.getRepository(OrderItem).findBy({ orderId: In(orders.map((o) => o.id)) }) : []
    return {
      items: orders.map((o) => toView(o, items.filter((i) => i.orderId === o.id))),
      total,
      page: query.page,
      limit: query.limit,
    }
  }

  /** Смена статуса под блокировкой строки: два админа одновременно не проведут заказ мимо правил. */
  async changeStatus(id: number, dto: ChangeStatusDto): Promise<OrderView> {
    return this.ds.transaction(async (m) => {
      const order = await m.findOne(Order, { where: { id }, lock: { mode: "pessimistic_write" } })
      if (!order) throw new DomainError(404, "ORDER_NOT_FOUND", `Заказ ${id} не найден`)
      if (!canTransition(order.status, dto.status)) {
        throw new DomainError(409, "INVALID_TRANSITION", `Нельзя перевести заказ из «${order.status}» в «${dto.status}»`, {
          from: order.status,
          to: dto.status,
          allowed: TRANSITIONS[order.status],
        })
      }
      order.status = dto.status
      await m.save(order)
      return this.get(id, m)
    })
  }
}
