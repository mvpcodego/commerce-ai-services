import { Global, Module } from "@nestjs/common"
import { TypeOrmModule } from "@nestjs/typeorm"
import { CatalogModule } from "./catalog/catalog.module.js"
import { AdminTokenGuard } from "./common/admin-token.guard.js"
import { APP_CONFIG, loadConfig, type AppConfig } from "./config.js"
import { dataSourceOptions } from "./db/data-source.js"
import { EventsModule } from "./events/events.module.js"
import { HealthModule } from "./health/health.module.js"
import { OrdersModule } from "./orders/orders.module.js"

@Global()
@Module({
  providers: [{ provide: APP_CONFIG, useFactory: () => loadConfig() }, AdminTokenGuard],
  exports: [APP_CONFIG, AdminTokenGuard],
})
class ConfigModule {}

@Module({
  imports: [
    ConfigModule,
    TypeOrmModule.forRootAsync({
      inject: [APP_CONFIG],
      useFactory: (config: AppConfig) => ({ ...dataSourceOptions(config.databaseUrl), retryAttempts: 3 }),
    }),
    EventsModule,
    CatalogModule,
    OrdersModule,
    HealthModule,
  ],
})
export class AppModule {}
