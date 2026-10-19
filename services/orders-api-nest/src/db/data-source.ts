import { DataSource, type DataSourceOptions } from "typeorm"
import { Car, Kit, Part } from "../catalog/catalog.entities.js"
import { IdempotencyKey, Order, OrderItem, OutboxEvent } from "../orders/orders.entities.js"
import { Init1760860800000 } from "./migrations/1760860800000-init.js"

export const ENTITIES = [Car, Part, Kit, Order, OrderItem, IdempotencyKey, OutboxEvent]

// Миграции перечислены явно, а не глобом: в ESM и после сборки путь к файлам не угадывается.
export function dataSourceOptions(url: string): DataSourceOptions {
  return {
    type: "postgres",
    url,
    entities: ENTITIES,
    migrations: [Init1760860800000],
    migrationsTableName: "typeorm_migrations",
    synchronize: false,
  }
}

export const createDataSource = (url: string) => new DataSource(dataSourceOptions(url))
