// Эталон для сверки: оригинальный TypeScript-расчёт на демо-данных.
import { readFileSync } from "node:fs"
import { planProcurement, summarizeProcurement } from "../../../lib/analytics/procurement.ts"

const d = JSON.parse(readFileSync(new URL("../../../seed/demo-data.json", import.meta.url), "utf8"))
const params = JSON.parse(process.argv[2])
const rows = planProcurement(d.orders, d.kits, d.parts, params)
console.log(JSON.stringify({ rows, summary: summarizeProcurement(rows, d.parts) }))
