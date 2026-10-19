import { Controller, Get, Inject } from "@nestjs/common"
import { ApiOperation, ApiTags } from "@nestjs/swagger"
import { InjectDataSource } from "@nestjs/typeorm"
import type { DataSource } from "typeorm"
import { DomainError } from "../common/domain-error.js"
import { APP_CONFIG, type AppConfig } from "../config.js"

@ApiTags("health")
@Controller("health")
export class HealthController {
  constructor(
    @InjectDataSource() private readonly ds: DataSource,
    @Inject(APP_CONFIG) private readonly config: AppConfig,
  ) {}

  @Get()
  @ApiOperation({ summary: "База доступна, сколько событий ждут публикации" })
  async check() {
    let outbox: { pending: number; oldest_pending_seconds: number | null }
    try {
      ;[outbox] = await this.ds.query<(typeof outbox)[]>(
        `SELECT count(*)::int AS pending, extract(epoch FROM now() - min(created_at))::int AS oldest_pending_seconds
         FROM outbox WHERE published_at IS NULL`,
      )
    } catch {
      throw new DomainError(503, "DB_UNAVAILABLE", "База данных недоступна")
    }
    return { status: "ok", db: "up", kafka: this.config.kafkaBrokers.length ? "configured" : "disabled", outbox }
  }
}
