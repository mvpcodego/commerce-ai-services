import { Inject, Injectable, Logger, type OnApplicationBootstrap, type OnApplicationShutdown } from "@nestjs/common"
import { InjectDataSource } from "@nestjs/typeorm"
import type { DataSource } from "typeorm"
import { APP_CONFIG, type AppConfig } from "../config.js"
import { EVENT_PUBLISHER, type EventPublisher } from "./event-publisher.js"

type Row = { id: string; event_id: string; topic: string; message_key: string; payload: { type?: string }; attempts: number }

/**
 * Публикует события из outbox. Строки берутся FOR UPDATE SKIP LOCKED — несколько экземпляров API
 * не отправят одно событие одновременно. published_at ставится только после ответа брокера:
 * упали между отправкой и коммитом — событие уйдёт ещё раз (at-least-once, потребитель сверяет event_id).
 */
@Injectable()
export class OutboxRelay implements OnApplicationBootstrap, OnApplicationShutdown {
  private readonly log = new Logger("OutboxRelay")
  private timer: NodeJS.Timeout | null = null
  private running: Promise<unknown> | null = null

  constructor(
    @InjectDataSource() private readonly ds: DataSource,
    @Inject(EVENT_PUBLISHER) private readonly publisher: EventPublisher,
    @Inject(APP_CONFIG) private readonly config: AppConfig,
  ) {}

  onApplicationBootstrap(): void {
    if (!this.config.kafkaBrokers.length || this.config.outboxPollMs <= 0) {
      this.log.warn("Kafka не настроена — события копятся в outbox, релей не запущен")
      return
    }
    this.timer = setInterval(() => {
      if (this.running) return // прошлый цикл ещё идёт
      this.running = this.runOnce()
        .catch((e: unknown) => this.log.error(e instanceof Error ? e.message : String(e)))
        .finally(() => (this.running = null))
    }, this.config.outboxPollMs)
  }

  async onApplicationShutdown(): Promise<void> {
    if (this.timer) clearInterval(this.timer)
    await this.running
    await this.publisher.close()
  }

  async runOnce(batchSize = 100): Promise<{ published: number; failed: number }> {
    return this.ds.transaction(async (m) => {
      const rows = await m.query<Row[]>(
        `SELECT id, event_id, topic, message_key, payload, attempts FROM outbox
         WHERE published_at IS NULL AND available_at <= now()
         ORDER BY id LIMIT $1 FOR UPDATE SKIP LOCKED`,
        [batchSize],
      )
      if (!rows.length) return { published: 0, failed: 0 }
      const ids = rows.map((r) => r.id)
      try {
        await this.publisher.publish(
          rows.map((r) => ({
            topic: r.topic,
            key: r.message_key,
            value: JSON.stringify(r.payload),
            headers: { "event-id": r.event_id, "event-type": r.payload.type ?? "" },
          })),
        )
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        // Пауза перед повтором: 2, 4, 8 … секунд, не больше 5 минут.
        await m.query(
          `UPDATE outbox SET attempts = attempts + 1, last_error = $2,
             available_at = now() + make_interval(secs => least(300, power(2, attempts + 1)))
           WHERE id = ANY($1::bigint[])`,
          [ids, message.slice(0, 500)],
        )
        this.log.warn(`не отправлено ${ids.length} событий: ${message}`)
        return { published: 0, failed: ids.length }
      }
      await m.query(
        `UPDATE outbox SET published_at = now(), attempts = attempts + 1, last_error = NULL WHERE id = ANY($1::bigint[])`,
        [ids],
      )
      return { published: ids.length, failed: 0 }
    })
  }
}
