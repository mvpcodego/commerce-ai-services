import { DomainError } from "../common/domain-error.js"
import type { Sellable } from "../catalog/catalog.service.js"
import { priceOrder } from "./pricing.js"

const catalog = new Map<string, Sellable>([
  ["kit-1", { sku: "kit-1", title: "Комплект", priceKopecks: 3_406_000 }],
  ["CAM-1", { sku: "CAM-1", title: "Камера", priceKopecks: 199_990 }],
])

describe("цена заказа", () => {
  it("цены из каталога, суммы в целых копейках", () => {
    const { lines, totalKopecks } = priceOrder([{ sku: "kit-1", quantity: 1 }, { sku: "CAM-1", quantity: 3 }], catalog)
    expect(lines.map((l) => [l.position, l.sku, l.lineTotalKopecks])).toEqual([[1, "kit-1", 3_406_000], [2, "CAM-1", 599_970]])
    expect(totalKopecks).toBe(4_005_970)
    expect(Number.isInteger(totalKopecks)).toBe(true)
  })

  it("неизвестные артикулы — 422 со списком всех неизвестных", () => {
    try {
      priceOrder([{ sku: "kit-1", quantity: 1 }, { sku: "NOPE", quantity: 1 }, { sku: "GONE", quantity: 1 }], catalog)
      throw new Error("не бросило")
    } catch (e) {
      expect(e).toBeInstanceOf(DomainError)
      expect((e as DomainError).status).toBe(422)
      expect((e as DomainError).details).toEqual({ skus: ["NOPE", "GONE"] })
    }
  })
})
