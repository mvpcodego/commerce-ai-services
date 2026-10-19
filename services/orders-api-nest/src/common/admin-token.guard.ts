import { CanActivate, ExecutionContext, Inject, Injectable, UnauthorizedException } from "@nestjs/common"
import { createHash, timingSafeEqual } from "node:crypto"
import type { Request } from "express"
import { APP_CONFIG, type AppConfig } from "../config.js"

const digest = (s: string) => createHash("sha256").update(s).digest()

/**
 * Админские маршруты (список заказов с телефонами, смена статуса) — только с токеном админки.
 * Оформление заказа и каталог открыты: это витрина.
 */
@Injectable()
export class AdminTokenGuard implements CanActivate {
  constructor(@Inject(APP_CONFIG) private readonly config: AppConfig) {}

  canActivate(context: ExecutionContext): boolean {
    const header = context.switchToHttp().getRequest<Request>().headers.authorization ?? ""
    const token = header.startsWith("Bearer ") ? header.slice(7) : ""
    // Сравнение хэшей фиксированной длины: время ответа не выдаёт, сколько символов совпало.
    if (!token || !timingSafeEqual(digest(token), digest(this.config.adminToken))) {
      throw new UnauthorizedException({ code: "UNAUTHORIZED", message: "Нужен токен админки: Authorization: Bearer <token>" })
    }
    return true
  }
}
