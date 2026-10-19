import type { ValueTransformer } from "typeorm"

/** bigint из pg приходит строкой. Суммы в копейках укладываются в Number.MAX_SAFE_INTEGER с огромным запасом. */
export const bigintToNumber: ValueTransformer = {
  to: (value: number | null | undefined) => value,
  from: (value: string | null) => (value === null ? null : Number(value)),
}
