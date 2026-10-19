import type { ExecutionContext } from "@nestjs/common"
import { loadConfig } from "../config.js"
import { AdminTokenGuard } from "./admin-token.guard.js"

const guard = new AdminTokenGuard(loadConfig({ ADMIN_API_TOKEN: "test-admin-token-0123456789" }))
const ctx = (authorization?: string) =>
  ({ switchToHttp: () => ({ getRequest: () => ({ headers: { authorization } }) }) }) as unknown as ExecutionContext

describe("токен админки", () => {
  it("верный Bearer — пропускает", () => {
    expect(guard.canActivate(ctx("Bearer test-admin-token-0123456789"))).toBe(true)
  })

  it.each([undefined, "", "Bearer ", "Bearer wrong", "test-admin-token-0123456789", "Basic dGVzdA=="])("%p — 401", (header) => {
    expect(() => guard.canActivate(ctx(header))).toThrow("токен админки")
  })

  it("без токена в окружении приложение не стартует", () => {
    expect(() => loadConfig({})).toThrow("ADMIN_API_TOKEN")
    expect(() => loadConfig({ ADMIN_API_TOKEN: "short" })).toThrow("ADMIN_API_TOKEN")
  })
})
