import { Column, CreateDateColumn, Entity, PrimaryColumn, PrimaryGeneratedColumn, UpdateDateColumn } from "typeorm"
import { bigintToNumber } from "../common/bigint.transformer.js"
import type { OrderStatus } from "./order-status.js"

@Entity({ name: "orders" })
export class Order {
  @PrimaryGeneratedColumn("increment") id: number
  @Column("text") status: OrderStatus
  @Column("text", { name: "customer_name" }) customerName: string
  @Column("text", { name: "customer_phone" }) customerPhone: string
  @Column("text", { name: "customer_city", nullable: true }) customerCity: string | null
  @Column("bigint", { name: "total_kopecks", transformer: bigintToNumber }) totalKopecks: number
  @CreateDateColumn({ name: "created_at", type: "timestamptz" }) createdAt: Date
  @UpdateDateColumn({ name: "updated_at", type: "timestamptz" }) updatedAt: Date
}

@Entity({ name: "order_items" })
export class OrderItem {
  @PrimaryGeneratedColumn("increment") id: number
  @Column("int", { name: "order_id" }) orderId: number
  @Column("int") position: number
  @Column("text") sku: string
  @Column("text") title: string
  @Column("int", { name: "unit_price_kopecks" }) unitPriceKopecks: number
  @Column("int") quantity: number
  @Column("bigint", { name: "line_total_kopecks", transformer: bigintToNumber }) lineTotalKopecks: number
}

/** Ключ идемпотентности: хэш тела и сохранённый ответ для повтора. */
@Entity({ name: "idempotency_keys" })
export class IdempotencyKey {
  @PrimaryColumn("text") key: string
  @Column("text", { name: "request_hash" }) requestHash: string
  @Column("int", { name: "order_id", nullable: true }) orderId: number | null
  @Column("jsonb", { nullable: true }) response: unknown
  @CreateDateColumn({ name: "created_at", type: "timestamptz" }) createdAt: Date
}

/** Outbox: событие пишется в той же транзакции, что и заказ; публикует OutboxRelay. */
@Entity({ name: "outbox" })
export class OutboxEvent {
  @PrimaryGeneratedColumn("increment", { type: "bigint" }) id: string
  @Column("uuid", { name: "event_id" }) eventId: string
  @Column("text") topic: string
  @Column("text", { name: "message_key" }) messageKey: string
  @Column("jsonb") payload: object
  @CreateDateColumn({ name: "created_at", type: "timestamptz" }) createdAt: Date
  @Column("timestamptz", { name: "available_at" }) availableAt: Date
  @Column("timestamptz", { name: "published_at", nullable: true }) publishedAt: Date | null
  @Column("int") attempts: number
  @Column("text", { name: "last_error", nullable: true }) lastError: string | null
}
