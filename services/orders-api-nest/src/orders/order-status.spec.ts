import { canTransition, ORDER_STATUSES, TRANSITIONS } from "./order-status.js"

describe("переходы статусов", () => {
  it.each([
    ["new", "confirmed"],
    ["new", "cancelled"],
    ["confirmed", "shipped"],
    ["confirmed", "cancelled"],
    ["shipped", "delivered"],
  ] as const)("%s → %s разрешён", (from, to) => {
    expect(canTransition(from, to)).toBe(true)
  })

  it.each([
    ["new", "shipped"],
    ["new", "delivered"],
    ["shipped", "cancelled"],
    ["delivered", "new"],
    ["cancelled", "confirmed"],
    ["confirmed", "confirmed"],
  ] as const)("%s → %s запрещён", (from, to) => {
    expect(canTransition(from, to)).toBe(false)
  })

  it("delivered и cancelled — конечные", () => {
    expect(TRANSITIONS.delivered).toEqual([])
    expect(TRANSITIONS.cancelled).toEqual([])
  })

  it("каждый статус описан, переходы ведут только в известные статусы", () => {
    expect(Object.keys(TRANSITIONS).sort()).toEqual([...ORDER_STATUSES].sort())
    for (const targets of Object.values(TRANSITIONS)) for (const t of targets) expect(ORDER_STATUSES).toContain(t)
  })
})
