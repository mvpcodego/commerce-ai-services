import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger"
import { Transform, Type } from "class-transformer"
import {
  ArrayMaxSize, ArrayMinSize, ArrayUnique, IsArray, IsIn, IsInt, IsOptional, IsString, Length,
  Matches, Max, MaxLength, Min, ValidateNested,
} from "class-validator"
import { PageQuery } from "../../common/pagination.js"
import { ORDER_STATUSES, type OrderStatus } from "../order-status.js"

const trim = ({ value }: { value: unknown }) => (typeof value === "string" ? value.trim() : value)

/** «+7 (900) 000-00-00», «8 900 …» → «79000000000». */
export function normalizePhone(value: unknown): unknown {
  if (typeof value !== "string") return value
  const digits = value.replace(/\D/g, "")
  return digits.length === 11 && digits.startsWith("8") ? `7${digits.slice(1)}` : digits
}

export class CustomerDto {
  @ApiProperty({ example: "Роман Ершов" })
  @Transform(trim)
  @IsString()
  @Length(2, 100)
  name: string

  @ApiProperty({ example: "+7 900 000-00-00", description: "Российский номер, сохраняется как 7XXXXXXXXXX" })
  @Transform(({ value }) => normalizePhone(value))
  @IsString()
  @Matches(/^7\d{10}$/, { message: "phone: нужен российский номер из 11 цифр" })
  phone: string

  @ApiPropertyOptional({ example: "Казань" })
  @IsOptional()
  @Transform(trim)
  @IsString()
  @MaxLength(100)
  city?: string
}

export class OrderItemDto {
  @ApiProperty({ example: "kit-47", description: "Артикул позиции или комплекта (kit-<id>)" })
  @IsString()
  @Length(1, 64)
  sku: string

  @ApiProperty({ example: 1, minimum: 1, maximum: 99 })
  @IsInt()
  @Min(1)
  @Max(99)
  quantity: number
}

export class CreateOrderDto {
  @ApiProperty({ type: CustomerDto })
  @ValidateNested()
  @Type(() => CustomerDto)
  customer: CustomerDto

  @ApiProperty({ type: [OrderItemDto], description: "1–50 строк, артикулы не повторяются. Цены не передаются — берутся из каталога." })
  @IsArray()
  @ArrayMinSize(1)
  @ArrayMaxSize(50)
  @ArrayUnique((i: OrderItemDto) => i?.sku, { message: "items: артикул повторяется — укажите количество в одной строке" })
  @ValidateNested({ each: true })
  @Type(() => OrderItemDto)
  items: OrderItemDto[]
}

export class ListOrdersQuery extends PageQuery {
  @ApiPropertyOptional({ enum: ORDER_STATUSES })
  @IsOptional()
  @IsIn(ORDER_STATUSES)
  status?: OrderStatus
}

export class ChangeStatusDto {
  @ApiProperty({ enum: ORDER_STATUSES })
  @IsIn(ORDER_STATUSES)
  status: OrderStatus
}

// Ответы — для схемы OpenAPI и типизации фронтенда.
export class OrderItemView {
  @ApiProperty() sku: string
  @ApiProperty() title: string
  @ApiProperty({ description: "Цена за штуку, копейки" }) unitPriceKopecks: number
  @ApiProperty() quantity: number
  @ApiProperty({ description: "Сумма строки, копейки" }) lineTotalKopecks: number
}

export class CustomerView {
  @ApiProperty() name: string
  @ApiProperty() phone: string
  @ApiProperty({ type: String, nullable: true }) city: string | null
}

export class OrderView {
  @ApiProperty() id: number
  @ApiProperty({ enum: ORDER_STATUSES }) status: OrderStatus
  @ApiProperty({ enum: ORDER_STATUSES, isArray: true, description: "Куда можно перевести заказ сейчас" })
  allowedTransitions: OrderStatus[]
  @ApiProperty({ type: CustomerView }) customer: CustomerView
  @ApiProperty({ type: [OrderItemView] }) items: OrderItemView[]
  @ApiProperty({ description: "Итого, копейки" }) totalKopecks: number
  @ApiProperty() createdAt: string
  @ApiProperty() updatedAt: string
}

export class OrderPage {
  @ApiProperty({ type: [OrderView] }) items: OrderView[]
  @ApiProperty() total: number
  @ApiProperty() page: number
  @ApiProperty() limit: number
}
