import "reflect-metadata"
import { NestFactory } from "@nestjs/core"
import { AppModule } from "./app.module.js"
import { setupApp } from "./app.setup.js"
import { APP_CONFIG, type AppConfig } from "./config.js"

const app = await NestFactory.create(AppModule)
setupApp(app)
const { port } = app.get<AppConfig>(APP_CONFIG)
await app.listen(port)
console.log(`orders-api-nest: http://localhost:${port}  (OpenAPI: /docs)`)
