/**
 * Что заканчивается и что заказывать.
 *
 * Главное здесь — раскрытие комплектов. Покупатель берёт «Kia Rio + Aurio S3»,
 * а со склада уходят четыре разные позиции: головное устройство, рамка,
 * проводка и стартовый набор. Если считать расход по строкам заказа, как они
 * записаны, то по складским позициям продаж не видно вообще, и раздел закупок
 * показывает пустоту при живом обороте.
 */

export type ProcurementOrder = {
  items: { sku: string; quantity: number }[]
  status: string
  created_at: string
}

export type ProcurementPart = {
  id: number
  sku: string
  title: string
  type: string
  stock: number
  price_retail: number | null
  archived?: boolean
}

export type ProcurementKit = {
  id: number
  head_unit_id: number
  frame_id: number | null
  wiring_id: number | null
  starter_kit_id: number | null
}

export type ProcurementState = "out" | "critical" | "low" | "ok" | "idle"

export type ProcurementRow = {
  sku: string
  title: string
  type: string
  stock: number
  sold: number
  perDay: number
  daysLeft: number | null
  reorder: number
  state: ProcurementState
}

export const PROCUREMENT_STATES: Record<ProcurementState, { label: string; hint: string }> = {
  out: {
    label: "Нет на складе",
    hint: "Позицию покупают, а остатка нет. Каждый день без неё — отказ клиенту.",
  },
  critical: {
    label: "Кончается",
    hint: "Запаса меньше, чем идёт поставка. Заказывать сейчас, иначе будет разрыв.",
  },
  low: {
    label: "На исходе",
    hint: "Запаса не хватит на весь горизонт планирования. Ставить в ближайшую заявку.",
  },
  ok: { label: "В норме", hint: "Запаса достаточно на горизонт планирования." },
  idle: {
    label: "Не продаётся",
    hint: "Остаток есть, спроса за период нет. Деньги стоят на полке.",
  },
}

/** Расход складских позиций за период: комплекты разложены на составляющие. */
export function consumption(
  orders: ProcurementOrder[],
  kits: ProcurementKit[],
  parts: ProcurementPart[],
): Map<string, number> {
  const partById = new Map(parts.map((p) => [p.id, p]))
  const kitParts = new Map<number, string[]>()
  for (const kit of kits) {
    const skus = [kit.head_unit_id, kit.frame_id, kit.wiring_id, kit.starter_kit_id]
      .filter((id): id is number => !!id)
      .map((id) => partById.get(id)?.sku)
      .filter((sku): sku is string => !!sku)
    kitParts.set(kit.id, skus)
  }

  const sold = new Map<string, number>()
  const add = (sku: string, qty: number) => sold.set(sku, (sold.get(sku) ?? 0) + qty)

  for (const order of orders) {
    // Отменённый заказ склад не покидал — спросом он тоже не является.
    if (order.status === "cancelled") continue
    for (const item of order.items ?? []) {
      const kitId = item.sku.startsWith("kit-") ? Number(item.sku.slice(4)) : null
      if (kitId !== null && !Number.isNaN(kitId)) {
        for (const sku of kitParts.get(kitId) ?? []) add(sku, item.quantity)
      } else {
        add(item.sku, item.quantity)
      }
    }
  }
  return sold
}

function stateOf(
  stock: number,
  sold: number,
  daysLeft: number | null,
  leadDays: number,
  horizonDays: number,
): ProcurementState {
  if (sold === 0) return stock > 0 ? "idle" : "ok"
  if (stock <= 0) return "out"
  if (daysLeft === null) return "ok"
  if (daysLeft <= leadDays) return "critical"
  // Граница «в норме» — это весь горизонт планирования, а не круглое число:
  // иначе позиция, которой хватит на 35 дней при потребности на 44, попадала
  // в норму и при этом требовала дозаказа. Сводка противоречила сама себе.
  if (daysLeft <= leadDays + horizonDays) return "low"
  return "ok"
}

/**
 * Считает потребность в закупке.
 *
 * `days` — окно, по которому меряем спрос; `leadDays` — сколько идёт поставка;
 * `horizonDays` — на сколько вперёд хотим иметь запас. Заказываем столько,
 * чтобы хватило на время поставки плюс горизонт, за вычетом того, что уже есть.
 */
export function planProcurement(
  orders: ProcurementOrder[],
  kits: ProcurementKit[],
  parts: ProcurementPart[],
  { days = 90, leadDays = 14, horizonDays = 30 } = {},
): ProcurementRow[] {
  const sold = consumption(orders, kits, parts)

  return parts
    .filter((p) => !p.archived)
    .map((part) => {
      const count = sold.get(part.sku) ?? 0
      const perDay = count / days
      const daysLeft = perDay > 0 ? Math.floor(part.stock / perDay) : null
      const need = Math.ceil(perDay * (leadDays + horizonDays))
      return {
        sku: part.sku,
        title: part.title,
        type: part.type,
        stock: part.stock,
        sold: count,
        perDay: Math.round(perDay * 100) / 100,
        daysLeft,
        reorder: Math.max(0, need - part.stock),
        state: stateOf(part.stock, count, daysLeft, leadDays, horizonDays),
      }
    })
    .sort((a, b) => {
      // Сначала то, что горит: сперва по остроте, внутри — по спросу.
      const order: ProcurementState[] = ["out", "critical", "low", "idle", "ok"]
      const diff = order.indexOf(a.state) - order.indexOf(b.state)
      return diff !== 0 ? diff : b.sold - a.sold
    })
}

/** Сводка по состояниям: сколько позиций и на какую сумму надо дозаказать. */
export function summarizeProcurement(rows: ProcurementRow[], parts: ProcurementPart[]) {
  const priceBySku = new Map(parts.map((p) => [p.sku, p.price_retail ?? 0]))
  const groups = new Map<ProcurementState, { positions: number; units: number; amount: number }>()

  for (const row of rows) {
    const entry = groups.get(row.state) ?? { positions: 0, units: 0, amount: 0 }
    entry.positions += 1
    entry.units += row.reorder
    entry.amount += row.reorder * (priceBySku.get(row.sku) ?? 0)
    groups.set(row.state, entry)
  }

  return (Object.keys(PROCUREMENT_STATES) as ProcurementState[])
    .map((key) => ({
      key,
      label: PROCUREMENT_STATES[key].label,
      hint: PROCUREMENT_STATES[key].hint,
      ...(groups.get(key) ?? { positions: 0, units: 0, amount: 0 }),
    }))
    .filter((g) => g.positions > 0)
}
