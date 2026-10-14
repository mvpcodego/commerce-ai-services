import { randomUUID } from "node:crypto"
import { Kafka, Partitioners, type Producer } from "kafkajs"

/**
 * Событие «заказ оформлен» в Kafka для сервиса ops (services/ops/ops/events.py).
 *
 * Без KAFKA_BROKERS ничего не отправляется. Ошибка брокера не роняет оформление:
 * заказ уже сохранён, а пересчёт закупок всё равно запускается по расписанию.
 * В событии нет имени и телефона покупателя: ops они не нужны, и база их ops не показывает.
 */

export const ORDERS_TOPIC = "orders"

export type OrderCreatedEvent = {
  event_id: string
  type: "order.created"
  occurred_at: string
  order_id: number | string
  items: { sku: string; quantity: number }[]
  total: number
}

let producer: Promise<Producer> | null = null

function getProducer(brokers: string): Promise<Producer> {
  producer ??= (async () => {
    const kafka = new Kafka({ clientId: "tmgoods-web", brokers: brokers.split(",") })
    // Идемпотентный продюсер: повтор отправки после сбоя сети не создаёт дубль в топике.
    const p = kafka.producer({
      idempotent: true,
      maxInFlightRequests: 1,
      createPartitioner: Partitioners.DefaultPartitioner,
    })
    await p.connect()
    return p
  })().catch((error) => {
    producer = null // следующая попытка подключится заново
    throw error
  })
  return producer
}

export function orderCreatedEvent(order: {
  id: number | string
  items: { sku: string; quantity: number }[]
  total: number
}): OrderCreatedEvent {
  return {
    event_id: randomUUID(),
    type: "order.created",
    occurred_at: new Date().toISOString(),
    order_id: order.id,
    items: order.items.map(({ sku, quantity }) => ({ sku, quantity })),
    total: order.total,
  }
}

export async function publishOrderCreated(order: Parameters<typeof orderCreatedEvent>[0]): Promise<void> {
  const brokers = process.env.KAFKA_BROKERS
  if (!brokers) return
  const event = orderCreatedEvent(order)
  try {
    const p = await getProducer(brokers)
    // Ключ — id заказа: события одного заказа попадают в одну партицию и идут по порядку.
    await p.send({ topic: ORDERS_TOPIC, messages: [{ key: String(order.id), value: JSON.stringify(event) }] })
  } catch (error) {
    console.error("order.created не отправлено:", error instanceof Error ? error.message : error)
  }
}
