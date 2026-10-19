import { readFile } from "node:fs/promises"
import { resolve } from "node:path"
import type { DataSource, EntityManager } from "typeorm"

// src/db и dist/db лежат на одной глубине — путь до корня репозитория одинаковый.
export const DEFAULT_SEED_FILE = resolve(import.meta.dirname, "../../../../seed/demo-data.json")

type SeedData = {
  cars: { id: number; make: string; model: string; generation: string | null; year_from: number | null; year_to: number | null; slug: string }[]
  parts: {
    id: number
    sku: string
    type: string
    title: string
    brand: string | null
    specs: Record<string, unknown> | null
    price_retail: number
    stock: number
    archived: boolean
    image_url: string | null
  }[]
  kits: {
    id: number
    car_id: number
    head_unit_id: number
    frame_id: number
    wiring_id: number
    starter_kit_id: number | null
    title: string
    price_retail: number
    is_default: boolean
  }[]
  orders: {
    id: number
    items: { sku: string; title: string; price: number; quantity: number }[]
    customer: { name: string; phone: string; city?: string }
    total: number
    status: string
    created_at: string
  }[]
}

const rub = (value: number) => Math.round(value * 100) // в seed цены в рублях, в базе — копейки

async function insertChunks(m: EntityManager, sql: (placeholders: string) => string, rows: unknown[][]): Promise<void> {
  const width = rows[0]?.length ?? 0
  for (let i = 0; i < rows.length; i += 500) {
    const chunk = rows.slice(i, i + 500)
    const placeholders = chunk.map((_, r) => `(${Array.from({ length: width }, (_, c) => `$${r * width + c + 1}`).join(", ")})`).join(", ")
    await m.query(sql(placeholders), chunk.flat())
  }
}

export type SeedResult = { cars: number; parts: number; kits: number; orders: number; ordersSkipped: boolean }

/**
 * Каталог — upsert по id (повторный запуск обновляет цены и остатки).
 * Исторические заказы — только в пустую таблицу, чтобы не смешать их с новыми.
 */
export async function seed(ds: DataSource, file = DEFAULT_SEED_FILE, withOrders = true): Promise<SeedResult> {
  const data = JSON.parse(await readFile(file, "utf8")) as SeedData
  return ds.transaction(async (m) => {
    await insertChunks(
      m,
      (v) => `INSERT INTO cars (id, make, model, generation, year_from, year_to, slug) VALUES ${v}
        ON CONFLICT (id) DO UPDATE SET make = EXCLUDED.make, model = EXCLUDED.model, generation = EXCLUDED.generation,
          year_from = EXCLUDED.year_from, year_to = EXCLUDED.year_to, slug = EXCLUDED.slug`,
      data.cars.map((c) => [c.id, c.make, c.model, c.generation, c.year_from, c.year_to, c.slug]),
    )
    await insertChunks(
      m,
      (v) => `INSERT INTO parts (id, sku, type, title, brand, specs, price_kopecks, stock, archived, image_url) VALUES ${v}
        ON CONFLICT (id) DO UPDATE SET sku = EXCLUDED.sku, type = EXCLUDED.type, title = EXCLUDED.title, brand = EXCLUDED.brand,
          specs = EXCLUDED.specs, price_kopecks = EXCLUDED.price_kopecks, stock = EXCLUDED.stock,
          archived = EXCLUDED.archived, image_url = EXCLUDED.image_url`,
      data.parts.map((p) => [p.id, p.sku, p.type, p.title, p.brand, JSON.stringify(p.specs ?? {}), rub(p.price_retail), p.stock, p.archived, p.image_url]),
    )
    await insertChunks(
      m,
      (v) => `INSERT INTO kits (id, sku, car_id, head_unit_id, frame_id, wiring_id, starter_kit_id, title, price_kopecks, is_default) VALUES ${v}
        ON CONFLICT (id) DO UPDATE SET sku = EXCLUDED.sku, car_id = EXCLUDED.car_id, head_unit_id = EXCLUDED.head_unit_id,
          frame_id = EXCLUDED.frame_id, wiring_id = EXCLUDED.wiring_id, starter_kit_id = EXCLUDED.starter_kit_id,
          title = EXCLUDED.title, price_kopecks = EXCLUDED.price_kopecks, is_default = EXCLUDED.is_default`,
      data.kits.map((k) => [k.id, `kit-${k.id}`, k.car_id, k.head_unit_id, k.frame_id, k.wiring_id, k.starter_kit_id, k.title, rub(k.price_retail), k.is_default]),
    )

    const [{ n }] = await m.query<{ n: number }[]>(`SELECT count(*)::int AS n FROM orders`)
    const ordersSkipped = !withOrders || n > 0
    if (!ordersSkipped) {
      await insertChunks(
        m,
        (v) => `INSERT INTO orders (id, status, customer_name, customer_phone, customer_city, total_kopecks, created_at, updated_at) VALUES ${v}`,
        data.orders.map((o) => [o.id, o.status, o.customer.name, o.customer.phone, o.customer.city ?? null, rub(o.total), o.created_at, o.created_at]),
      )
      await insertChunks(
        m,
        (v) => `INSERT INTO order_items (order_id, position, sku, title, unit_price_kopecks, quantity, line_total_kopecks) VALUES ${v}`,
        data.orders.flatMap((o) => o.items.map((i, pos) => [o.id, pos + 1, i.sku, i.title, rub(i.price), i.quantity, rub(i.price) * i.quantity])),
      )
      // Новые заказы получают id после исторических.
      await m.query(`SELECT setval(pg_get_serial_sequence('orders', 'id'), (SELECT max(id) FROM orders))`)
    }
    return { cars: data.cars.length, parts: data.parts.length, kits: data.kits.length, orders: ordersSkipped ? 0 : data.orders.length, ordersSkipped }
  })
}
