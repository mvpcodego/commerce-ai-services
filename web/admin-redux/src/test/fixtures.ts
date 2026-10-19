import type { Car, Kit, Order, OrderStatus, Part } from '../api/types'

const TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  new: ['confirmed', 'cancelled'],
  confirmed: ['shipped', 'cancelled'],
  shipped: ['delivered'],
  delivered: [],
  cancelled: [],
}

export function makeOrder(id: number, status: OrderStatus = 'new', overrides: Partial<Order> = {}): Order {
  return {
    id,
    status,
    allowedTransitions: TRANSITIONS[status],
    customer: { name: `Клиент ${id}`, phone: '79000000001', city: 'Казань' },
    items: [{ sku: 'kit-47', title: 'Hyundai Solaris + Nordvox N2 9"', unitPriceKopecks: 3550000, quantity: 1, lineTotalKopecks: 3550000 }],
    totalKopecks: 3550000,
    createdAt: '2026-10-19T10:45:59.210Z',
    updatedAt: '2026-10-19T10:45:59.210Z',
    ...overrides,
  }
}

export const cars: Car[] = [
  { id: 1, make: 'Hyundai', model: 'Solaris', generation: 'II', yearFrom: 2017, yearTo: 2022, slug: 'hyundai-solaris-2' },
  { id: 2, make: 'Kia', model: 'Rio', generation: null, yearFrom: null, yearTo: null, slug: 'kia-rio' },
]

export const kits: Kit[] = [
  { id: 47, sku: 'kit-47', carId: 1, title: 'Hyundai Solaris + Nordvox N2 9"', priceKopecks: 3550000, isDefault: true },
]

export const parts: Part[] = [
  { id: 5, sku: 'CAM-01', type: 'camera', title: 'Камера заднего вида', brand: null, priceKopecks: 199000, stock: 3 },
]

export function apiError(statusCode: number, code: string, message: string, details?: unknown) {
  return { statusCode, code, message, details, path: '/test', timestamp: '2026-10-19T10:45:59.314Z' }
}
