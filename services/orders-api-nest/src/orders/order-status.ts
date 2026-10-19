export const ORDER_STATUSES = ["new", "confirmed", "shipped", "delivered", "cancelled"] as const
export type OrderStatus = (typeof ORDER_STATUSES)[number]

/** Разрешённые переходы. delivered и cancelled — конечные. Отменить можно только до отгрузки. */
export const TRANSITIONS: Readonly<Record<OrderStatus, readonly OrderStatus[]>> = {
  new: ["confirmed", "cancelled"],
  confirmed: ["shipped", "cancelled"],
  shipped: ["delivered"],
  delivered: [],
  cancelled: [],
}

export function canTransition(from: OrderStatus, to: OrderStatus): boolean {
  return TRANSITIONS[from].includes(to)
}
