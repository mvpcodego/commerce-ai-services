// Контракт orders-api-nest. Все суммы — целые копейки.

export const ORDER_STATUSES = ['new', 'confirmed', 'shipped', 'delivered', 'cancelled'] as const
export type OrderStatus = (typeof ORDER_STATUSES)[number]

export type Customer = { name: string; phone: string; city: string | null }

export type OrderItem = {
  sku: string
  title: string
  unitPriceKopecks: number
  quantity: number
  lineTotalKopecks: number
}

export type Order = {
  id: number
  status: OrderStatus
  allowedTransitions: OrderStatus[]
  customer: Customer
  items: OrderItem[]
  totalKopecks: number
  createdAt: string
  updatedAt: string
}

export type Page<T> = { items: T[]; total: number; page: number; limit: number }

export type ListOrdersArgs = { status?: OrderStatus; page: number; limit: number }

export type CreateOrderBody = {
  customer: { name: string; phone: string; city?: string }
  items: { sku: string; quantity: number }[]
}

export type CreateOrderResult = { order: Order; replayed: boolean }

export type Car = {
  id: number
  make: string
  model: string
  generation: string | null
  yearFrom: number | null
  yearTo: number | null
  slug: string
}

export type Part = {
  id: number
  sku: string
  type: string
  title: string
  brand: string | null
  priceKopecks: number
  stock: number
}

export type Kit = {
  id: number
  sku: string
  carId: number
  title: string
  priceKopecks: number
  isDefault: boolean
}

/** Единый формат ошибки API (ApiExceptionFilter). */
export type ApiErrorBody = {
  statusCode: number
  code: string
  message: string
  details?: unknown
  path: string
  timestamp: string
}
