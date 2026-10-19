export type AppConfig = {
  port: number
  databaseUrl: string
  adminToken: string
  corsOrigins: string[]
  kafkaBrokers: string[]
  outboxPollMs: number
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const adminToken = env.ADMIN_API_TOKEN ?? ""
  // Без токена админские маршруты были бы открыты всем — не стартуем.
  if (adminToken.length < 16) throw new Error("ADMIN_API_TOKEN не задан или короче 16 символов")
  return {
    port: Number(env.PORT ?? 3100),
    databaseUrl: env.DATABASE_URL ?? "postgres://orders:orders@localhost:5436/orders",
    adminToken,
    corsOrigins: (env.CORS_ORIGINS ?? "http://localhost:5173").split(",").map((s) => s.trim()).filter(Boolean),
    kafkaBrokers: (env.KAFKA_BROKERS ?? "").split(",").map((s) => s.trim()).filter(Boolean),
    outboxPollMs: Number(env.OUTBOX_POLL_MS ?? 1000),
  }
}

export const APP_CONFIG = Symbol("APP_CONFIG")
