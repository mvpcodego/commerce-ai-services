import { createHash } from "node:crypto"
import { DomainError } from "../common/domain-error.js"

export const IDEMPOTENCY_HEADER = "idempotency-key"
const KEY_RE = /^[A-Za-z0-9._:-]{8,255}$/

/** JSON с ключами по алфавиту: один и тот же объект всегда даёт одну строку и один хэш. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(",")}}`
  }
  return JSON.stringify(value)
}

export const requestHash = (body: unknown): string => createHash("sha256").update(canonicalJson(body)).digest("hex")

export function assertValidKey(key: string | undefined): string {
  if (!key) throw new DomainError(400, "IDEMPOTENCY_KEY_REQUIRED", "Нужен заголовок Idempotency-Key (например, UUID)")
  if (!KEY_RE.test(key)) {
    throw new DomainError(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key: 8–255 символов из A-Z a-z 0-9 . _ : -")
  }
  return key
}

/** Тот же ключ с другим телом — ошибка клиента, а не повтор. */
export function assertSameRequest(storedHash: string, hash: string): void {
  if (storedHash !== hash) {
    throw new DomainError(409, "IDEMPOTENCY_KEY_REUSED", "Этот Idempotency-Key уже использован с другим телом запроса")
  }
}
