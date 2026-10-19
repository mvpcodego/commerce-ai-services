import { jest } from "@jest/globals"
import { ArgumentsHost, BadRequestException, Logger, NotFoundException } from "@nestjs/common"
import { ApiExceptionFilter } from "./api-exception.filter.js"
import { DomainError } from "./domain-error.js"

function run(exception: unknown) {
  const res = { status: jest.fn().mockReturnThis(), json: jest.fn() }
  const host = {
    switchToHttp: () => ({ getRequest: () => ({ originalUrl: "/orders?page=1" }), getResponse: () => res }),
  } as unknown as ArgumentsHost
  new ApiExceptionFilter().catch(exception, host)
  return { status: res.status.mock.calls[0][0], body: res.json.mock.calls[0][0] as Record<string, unknown> }
}

describe("единый формат ошибок", () => {
  it("DomainError → свой статус, код и подробности", () => {
    const { status, body } = run(new DomainError(409, "INVALID_TRANSITION", "нельзя", { allowed: [] }))
    expect(status).toBe(409)
    expect(body).toMatchObject({ statusCode: 409, code: "INVALID_TRANSITION", message: "нельзя", details: { allowed: [] }, path: "/orders?page=1" })
    expect(typeof body.timestamp).toBe("string")
  })

  it("HttpException с кодом (ValidationPipe) и без кода (Nest)", () => {
    expect(run(new BadRequestException({ code: "VALIDATION_FAILED", message: "x", details: [1] })).body).toMatchObject({ code: "VALIDATION_FAILED", details: [1] })
    expect(run(new NotFoundException("Cannot GET /nope")).body).toMatchObject({ statusCode: 404, code: "NOT_FOUND" })
  })

  it("неизвестная ошибка — 500 без подробностей наружу", () => {
    jest.spyOn(Logger.prototype, "error").mockImplementation(() => undefined)
    const { status, body } = run(new Error("password=secret в стеке"))
    expect(status).toBe(500)
    expect(body).toMatchObject({ code: "INTERNAL" })
    expect(JSON.stringify(body)).not.toContain("secret")
  })
})
