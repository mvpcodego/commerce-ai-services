import { Kafka, logLevel, Partitioners, type Producer } from "kafkajs"
import type { EventPublisher, OutgoingMessage } from "./event-publisher.js"

export class KafkaPublisher implements EventPublisher {
  private producer: Promise<Producer> | null = null

  constructor(private readonly brokers: string[]) {}

  private connect(): Promise<Producer> {
    this.producer ??= (async () => {
      const kafka = new Kafka({ clientId: "orders-api-nest", brokers: this.brokers, logLevel: logLevel.WARN })
      // Идемпотентный продюсер: повтор после сетевого сбоя не даёт дубля внутри сессии продюсера.
      // Дубли между перезапусками релея отсекает потребитель по event_id.
      const p = kafka.producer({ idempotent: true, maxInFlightRequests: 1, createPartitioner: Partitioners.DefaultPartitioner })
      await p.connect()
      return p
    })().catch((error: unknown) => {
      this.producer = null // следующий цикл релея подключится заново
      throw error
    })
    return this.producer
  }

  async publish(messages: OutgoingMessage[]): Promise<void> {
    const producer = await this.connect()
    const byTopic = new Map<string, OutgoingMessage[]>()
    for (const m of messages) byTopic.set(m.topic, [...(byTopic.get(m.topic) ?? []), m])
    await producer.sendBatch({
      acks: -1,
      topicMessages: [...byTopic].map(([topic, list]) => ({
        topic,
        messages: list.map((m) => ({ key: m.key, value: m.value, headers: m.headers })),
      })),
    })
  }

  async close(): Promise<void> {
    if (!this.producer) return
    const p = await this.producer.catch(() => null)
    this.producer = null
    await p?.disconnect()
  }
}
