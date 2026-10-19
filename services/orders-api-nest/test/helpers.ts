import type { INestApplication } from "@nestjs/common"
import { Test } from "@nestjs/testing"
import { connect } from "node:net"
import pg from "pg"
import { AppModule } from "../src/app.module.js"
import { setupApp } from "../src/app.setup.js"
import { createDataSource } from "../src/db/data-source.js"
import { seed } from "../src/db/seed.js"
import { EVENT_PUBLISHER, InMemoryPublisher, type EventPublisher } from "../src/events/event-publisher.js"

export const TEST_DB_URL = process.env.TEST_DATABASE_URL ?? "postgres://orders:orders@localhost:5436/orders_test"
export const ADMIN_TOKEN = "e2e-admin-token-0123456789abcdef"

/** Создаёт тестовую базу рядом с рабочей. false — Postgres недоступен, e2e пропускаются. */
export async function testDatabaseReady(url = TEST_DB_URL): Promise<boolean> {
  const target = new URL(url)
  const name = target.pathname.slice(1)
  const admin = new URL(url)
  admin.pathname = "/postgres"
  const client = new pg.Client({ connectionString: admin.toString(), connectionTimeoutMillis: 2000 })
  try {
    await client.connect()
    const { rowCount } = await client.query("SELECT 1 FROM pg_database WHERE datname = $1", [name])
    if (!rowCount) await client.query(`CREATE DATABASE "${name.replace(/"/g, "")}"`)
    return true
  } catch {
    return false
  } finally {
    await client.end().catch(() => undefined)
  }
}

export function portOpen(hostPort: string, timeoutMs = 1500): Promise<boolean> {
  const [host, port] = hostPort.split(":")
  return new Promise((resolve) => {
    const socket = connect({ host, port: Number(port), timeout: timeoutMs })
    const done = (ok: boolean) => {
      socket.destroy()
      resolve(ok)
    }
    socket.once("connect", () => done(true)).once("error", () => done(false)).once("timeout", () => done(false))
  })
}

/** Миграции + каталог из seed, заказы и outbox пустые. */
export async function resetDatabase(): Promise<void> {
  const ds = createDataSource(TEST_DB_URL)
  await ds.initialize()
  try {
    await ds.runMigrations({ transaction: "each" })
    await ds.query("TRUNCATE outbox, idempotency_keys, order_items, orders RESTART IDENTITY CASCADE")
    await seed(ds, undefined, false)
  } finally {
    await ds.destroy()
  }
}

export async function createTestApp(publisher: EventPublisher = new InMemoryPublisher()): Promise<INestApplication> {
  Object.assign(process.env, {
    DATABASE_URL: TEST_DB_URL,
    ADMIN_API_TOKEN: ADMIN_TOKEN,
    KAFKA_BROKERS: "", // релей по таймеру не запускается, тесты вызывают runOnce сами
    CORS_ORIGINS: "http://localhost:5173",
  })
  const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).overrideProvider(EVENT_PUBLISHER).useValue(publisher).compile()
  const app = moduleRef.createNestApplication({ logger: ["error"] })
  setupApp(app)
  await app.listen(0) // один слушающий сервер: supertest не поднимает свой на каждый запрос
  return app
}
