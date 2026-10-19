import { Global, Module } from "@nestjs/common"
import { APP_CONFIG, type AppConfig } from "../config.js"
import { DisabledPublisher, EVENT_PUBLISHER } from "./event-publisher.js"
import { KafkaPublisher } from "./kafka.publisher.js"
import { OutboxRelay } from "./outbox.relay.js"

@Global()
@Module({
  providers: [
    {
      provide: EVENT_PUBLISHER,
      inject: [APP_CONFIG],
      useFactory: (config: AppConfig) => (config.kafkaBrokers.length ? new KafkaPublisher(config.kafkaBrokers) : new DisabledPublisher()),
    },
    OutboxRelay,
  ],
  exports: [EVENT_PUBLISHER, OutboxRelay],
})
export class EventsModule {}
