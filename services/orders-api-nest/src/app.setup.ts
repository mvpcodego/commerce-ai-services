import type { INestApplication } from "@nestjs/common"
import { DocumentBuilder, SwaggerModule } from "@nestjs/swagger"
import { ApiExceptionFilter } from "./common/api-exception.filter.js"
import { createValidationPipe } from "./common/validation.js"
import { APP_CONFIG, type AppConfig } from "./config.js"

/** Общая настройка для main.ts и e2e-тестов: тесты проверяют то же приложение, что запускается. */
export function setupApp(app: INestApplication): void {
  const config = app.get<AppConfig>(APP_CONFIG)
  app.useGlobalPipes(createValidationPipe())
  app.useGlobalFilters(new ApiExceptionFilter())
  app.enableCors({
    origin: config.corsOrigins,
    methods: ["GET", "POST", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization", "Idempotency-Key"],
    exposedHeaders: ["Idempotency-Replayed"],
  })
  app.enableShutdownHooks()
  const doc = new DocumentBuilder()
    .setTitle("orders-api-nest")
    .setDescription("API заказов магазина автомагнитол. Суммы — целые копейки. Ошибки — { statusCode, code, message, details?, path, timestamp }.")
    .setVersion("0.1.0")
    .addBearerAuth()
    .build()
  SwaggerModule.setup("docs", app, () => SwaggerModule.createDocument(app, doc))
}
