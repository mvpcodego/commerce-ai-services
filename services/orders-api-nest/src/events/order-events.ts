/**
 * Схема события совместима с потребителем services/ops (ops/events.py): event_id, type, occurred_at
 * с часовым поясом; ключ сообщения — id заказа. Сумма — в копейках, поле total_kopecks.
 */
export const ORDERS_TOPIC = "orders"

export type OrderCreatedEvent = {
  event_id: string
  type: "order.created"
  occurred_at: string
  order_id: number
  items: { sku: string; quantity: number }[]
  total_kopecks: number
}
