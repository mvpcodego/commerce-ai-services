import type { ArgumentMetadata, BadRequestException } from "@nestjs/common"
import { createValidationPipe } from "../../common/validation.js"
import { CreateOrderDto, ListOrdersQuery, normalizePhone } from "./order.dto.js"

const pipe = createValidationPipe()
const body: ArgumentMetadata = { type: "body", metatype: CreateOrderDto }

async function errorsOf(value: unknown): Promise<{ field: string; errors: string[] }[]> {
  try {
    await pipe.transform(value, body)
    return []
  } catch (e) {
    return ((e as BadRequestException).getResponse() as { details: { field: string; errors: string[] }[] }).details
  }
}

describe("валидация CreateOrderDto", () => {
  it("телефон нормализуется к 7XXXXXXXXXX, имя обрезается", async () => {
    const dto = (await pipe.transform(
      { customer: { name: "  Анна  ", phone: "8 (900) 000-00-01" }, items: [{ sku: "kit-1", quantity: 2 }] },
      body,
    )) as CreateOrderDto
    expect(dto.customer).toEqual({ name: "Анна", phone: "79000000001" })
    expect(normalizePhone("+7 900 000 00 01")).toBe("79000000001")
  })

  it("цену передать нельзя, артикулы не повторяются, количество 1–99", async () => {
    const fields = (await errorsOf({
      customer: { name: "Анна", phone: "79000000001" },
      items: [{ sku: "kit-1", quantity: 0, price: 1 }, { sku: "kit-1", quantity: 1.5 }],
    })).map((e) => e.field)
    expect(fields).toEqual(expect.arrayContaining(["items", "items.0.price", "items.0.quantity", "items.1.quantity"]))
  })

  it("пустой заказ и чужой номер — ошибки по полям", async () => {
    const fields = (await errorsOf({ customer: { name: "А", phone: "12345" }, items: [] })).map((e) => e.field)
    expect(fields).toEqual(expect.arrayContaining(["customer.name", "customer.phone", "items"]))
  })

  it("query: page/limit приводятся к числам, limit не больше 100, статус из списка", async () => {
    const q = (await pipe.transform({ page: "2", limit: "5", status: "new" }, { type: "query", metatype: ListOrdersQuery })) as ListOrdersQuery
    expect(q).toMatchObject({ page: 2, limit: 5, status: "new" })
    await expect(pipe.transform({ limit: "500", status: "lost" }, { type: "query", metatype: ListOrdersQuery })).rejects.toBeDefined()
  })
})
