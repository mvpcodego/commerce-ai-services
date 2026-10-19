import type { INestApplication } from "@nestjs/common"
import { Kafka, logLevel } from "kafkajs"
import { randomUUID } from "node:crypto"
import request from "supertest"
import type { App } from "supertest/types.js"
import { DataSource } from "typeorm"
import { KafkaPublisher } from "../src/events/kafka.publisher.js"
import { OutboxRelay } from "../src/events/outbox.relay.js"
import { createTestApp, portOpen, resetDatabase, testDatabaseReady } from "./helpers.js"

const BROKERS = (process.env.KAFKA_TEST_BROKERS ?? "localhost:9094").split(",")
const ready = (await testDatabaseReady()) && (await portOpen(BROKERS[0]))
if (!ready) console.warn("Postgres или Kafka недоступны (docker compose up -d) — живой прогон Kafka пропущен")
const describeKafka = ready ? describe : describe.skip

describeKafka("живая публикация в Kafka", () => {
  let app: INestApplication

  beforeAll(async () => {
    await resetDatabase()
    app = await createTestApp(new KafkaPublisher(BROKERS))
  })

  afterAll(async () => {
    await app?.close() // закрывает и продюсер (onApplicationShutdown релея)
  })

  it("заказ → outbox → топик orders: событие читается потребителем", async () => {
    const created = await request(app.getHttpServer() as App)
      .post("/orders")
      .set("Idempotency-Key", randomUUID())
      .send({ customer: { name: "Анна Котова", phone: "79000000002" }, items: [{ sku: "kit-12", quantity: 1 }] })
      .expect(201)

    expect(await app.get(OutboxRelay).runOnce()).toEqual({ published: 1, failed: 0 })
    // Ищем по event_id: id заказов в тестовой базе начинаются заново, а топик хранит прошлые прогоны.
    const [{ event_id: eventId }] = await app
      .get(DataSource)
      .query<{ event_id: string }[]>(`SELECT event_id FROM outbox WHERE message_key = $1`, [String(created.body.id)])

    const kafka = new Kafka({ clientId: "orders-e2e", brokers: BROKERS, logLevel: logLevel.NOTHING })
    const consumer = kafka.consumer({ groupId: `orders-e2e-${randomUUID()}` })
    await consumer.connect()
    await consumer.subscribe({ topic: "orders", fromBeginning: true })
    try {
      const found = await new Promise<{ key: string; value: Record<string, unknown> }>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("событие не пришло за 20 с")), 20000)
        void consumer.run({
          eachMessage: async ({ message }) => {
            const value = JSON.parse(message.value?.toString() ?? "{}") as Record<string, unknown>
            if (value.event_id === eventId) {
              clearTimeout(timer)
              resolve({ key: message.key?.toString() ?? "", value })
            }
          },
        })
      })
      expect(found.key).toBe(String(created.body.id))
      expect(found.value).toMatchObject({ type: "order.created", order_id: created.body.id, items: [{ sku: "kit-12", quantity: 1 }], total_kopecks: created.body.totalKopecks })
    } finally {
      await consumer.disconnect()
    }
  })
})
