import { DomainError } from "../common/domain-error.js"
import { assertSameRequest, assertValidKey, canonicalJson, requestHash } from "./idempotency.js"

describe("идемпотентность: хэш тела", () => {
  it("порядок ключей объекта не влияет на хэш", () => {
    const a = { customer: { name: "А", phone: "79000000000" }, items: [{ sku: "kit-1", quantity: 1 }] }
    const b = { items: [{ quantity: 1, sku: "kit-1" }], customer: { phone: "79000000000", name: "А" } }
    expect(canonicalJson(a)).toBe(canonicalJson(b))
    expect(requestHash(a)).toBe(requestHash(b))
  })

  it("undefined-поля не участвуют (необязательный city не задан = не передан)", () => {
    expect(requestHash({ city: undefined, name: "А" })).toBe(requestHash({ name: "А" }))
  })

  it("другое количество или порядок строк — другой хэш", () => {
    const base = { items: [{ sku: "a", quantity: 1 }, { sku: "b", quantity: 1 }] }
    expect(requestHash(base)).not.toBe(requestHash({ items: [{ sku: "a", quantity: 2 }, { sku: "b", quantity: 1 }] }))
    expect(requestHash(base)).not.toBe(requestHash({ items: [{ sku: "b", quantity: 1 }, { sku: "a", quantity: 1 }] }))
  })
})

describe("идемпотентность: ключ", () => {
  const codeOf = (fn: () => unknown) => {
    try {
      fn()
    } catch (e) {
      return e instanceof DomainError ? `${e.status} ${e.code}` : "other"
    }
    return "ok"
  }

  it("нет ключа — 400, кривой ключ — 400, UUID — ок", () => {
    expect(codeOf(() => assertValidKey(undefined))).toBe("400 IDEMPOTENCY_KEY_REQUIRED")
    expect(codeOf(() => assertValidKey("short"))).toBe("400 IDEMPOTENCY_KEY_INVALID")
    expect(codeOf(() => assertValidKey("ключ-кириллицей-1"))).toBe("400 IDEMPOTENCY_KEY_INVALID")
    expect(codeOf(() => assertValidKey("2f1c7a52-6a3e-4c1b-9d55-0c6c1f0b9a11"))).toBe("ok")
  })

  it("тот же ключ с другим телом — 409", () => {
    expect(codeOf(() => assertSameRequest("aaa", "aaa"))).toBe("ok")
    expect(codeOf(() => assertSameRequest("aaa", "bbb"))).toBe("409 IDEMPOTENCY_KEY_REUSED")
  })
})
