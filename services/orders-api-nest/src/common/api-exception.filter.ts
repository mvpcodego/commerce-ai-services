import { ArgumentsHost, Catch, ExceptionFilter, HttpException, HttpStatus, Logger } from "@nestjs/common"
import type { Request, Response } from "express"
import { DomainError } from "./domain-error.js"

/** Единый формат ошибки для всех маршрутов. */
export type ApiError = {
  statusCode: number
  code: string
  message: string
  details?: unknown
  path: string
  timestamp: string
}

const CODE_BY_STATUS: Record<number, string> = {
  400: "BAD_REQUEST",
  401: "UNAUTHORIZED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  409: "CONFLICT",
  413: "PAYLOAD_TOO_LARGE",
  422: "UNPROCESSABLE",
  503: "UNAVAILABLE",
}

@Catch()
export class ApiExceptionFilter implements ExceptionFilter {
  private readonly log = new Logger("ApiExceptionFilter")

  catch(exception: unknown, host: ArgumentsHost): void {
    const ctx = host.switchToHttp()
    const req = ctx.getRequest<Request>()
    const res = ctx.getResponse<Response>()
    const body = this.toBody(exception)
    if (body.statusCode >= 500) this.log.error(exception instanceof Error ? exception.stack : String(exception))
    res.status(body.statusCode).json({ ...body, path: req.originalUrl, timestamp: new Date().toISOString() } satisfies ApiError)
  }

  private toBody(exception: unknown): Omit<ApiError, "path" | "timestamp"> {
    if (exception instanceof DomainError) {
      return { statusCode: exception.status, code: exception.code, message: exception.message, details: exception.details }
    }
    if (exception instanceof HttpException) {
      const status = exception.getStatus()
      const payload = exception.getResponse()
      if (typeof payload === "object" && payload !== null && "code" in payload) {
        const p = payload as { code: string; message: string; details?: unknown }
        return { statusCode: status, code: p.code, message: p.message, details: p.details }
      }
      return { statusCode: status, code: CODE_BY_STATUS[status] ?? `HTTP_${status}`, message: exception.message }
    }
    // Неизвестное — наружу без подробностей, в лог целиком.
    return { statusCode: HttpStatus.INTERNAL_SERVER_ERROR, code: "INTERNAL", message: "Внутренняя ошибка сервера" }
  }
}
