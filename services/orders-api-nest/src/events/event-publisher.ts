export type OutgoingMessage = {
  topic: string
  key: string
  value: string
  headers: Record<string, string>
}

/** Куда релей отправляет события. Kafka в работе, память в тестах. */
export interface EventPublisher {
  publish(messages: OutgoingMessage[]): Promise<void>
  close(): Promise<void>
}

export const EVENT_PUBLISHER = Symbol("EVENT_PUBLISHER")

export class InMemoryPublisher implements EventPublisher {
  readonly sent: OutgoingMessage[] = []
  failNext = 0 // сколько следующих вызовов упадёт — для проверки повторов

  publish(messages: OutgoingMessage[]): Promise<void> {
    if (this.failNext > 0) {
      this.failNext--
      return Promise.reject(new Error("брокер недоступен (тест)"))
    }
    this.sent.push(...messages)
    return Promise.resolve()
  }

  close(): Promise<void> {
    return Promise.resolve()
  }
}

/** Kafka не настроена: события остаются в outbox, релей не запускается. */
export class DisabledPublisher implements EventPublisher {
  publish(): Promise<void> {
    return Promise.reject(new Error("KAFKA_BROKERS не задан"))
  }

  close(): Promise<void> {
    return Promise.resolve()
  }
}
