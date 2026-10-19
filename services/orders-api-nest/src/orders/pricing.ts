import { DomainError } from "../common/domain-error.js"
import type { Sellable } from "../catalog/catalog.service.js"

export type PricedLine = { position: number; sku: string; title: string; unitPriceKopecks: number; quantity: number; lineTotalKopecks: number }

/** Строки заказа по ценам каталога, всё в целых копейках. Неизвестный или архивный артикул — 422 со списком. */
export function priceOrder(
  items: { sku: string; quantity: number }[],
  catalog: Map<string, Sellable>,
): { lines: PricedLine[]; totalKopecks: number } {
  const missing = items.filter((i) => !catalog.has(i.sku)).map((i) => i.sku)
  if (missing.length) throw new DomainError(422, "UNKNOWN_SKU", "В каталоге нет таких артикулов (или они в архиве)", { skus: missing })
  const lines = items.map((item, index) => {
    const c = catalog.get(item.sku)!
    return {
      position: index + 1,
      sku: c.sku,
      title: c.title,
      unitPriceKopecks: c.priceKopecks,
      quantity: item.quantity,
      lineTotalKopecks: c.priceKopecks * item.quantity,
    }
  })
  return { lines, totalKopecks: lines.reduce((sum, l) => sum + l.lineTotalKopecks, 0) }
}
