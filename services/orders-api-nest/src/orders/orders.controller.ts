import { Body, Controller, Get, Headers, HttpCode, Param, ParseIntPipe, Patch, Post, Query, Res, UseGuards } from "@nestjs/common"
import { ApiBearerAuth, ApiHeader, ApiOkResponse, ApiCreatedResponse, ApiOperation, ApiTags } from "@nestjs/swagger"
import type { Response } from "express"
import { AdminTokenGuard } from "../common/admin-token.guard.js"
import { ChangeStatusDto, CreateOrderDto, ListOrdersQuery, OrderPage, OrderView } from "./dto/order.dto.js"
import { assertValidKey, IDEMPOTENCY_HEADER } from "./idempotency.js"
import { OrdersService } from "./orders.service.js"

@ApiTags("orders")
@Controller("orders")
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Post()
  @HttpCode(201)
  @ApiOperation({ summary: "Оформить заказ (витрина, без токена). Повтор с тем же ключом возвращает тот же ответ." })
  @ApiHeader({ name: "Idempotency-Key", required: true, description: "Уникальный ключ попытки оформления, например UUID" })
  @ApiCreatedResponse({ type: OrderView, description: "Заголовок Idempotency-Replayed: true — ответ на повтор" })
  async create(
    @Headers(IDEMPOTENCY_HEADER) key: string | undefined,
    @Body() dto: CreateOrderDto,
    @Res({ passthrough: true }) res: Response,
  ): Promise<OrderView> {
    const { order, replayed } = await this.orders.create(assertValidKey(key), dto)
    res.setHeader("Idempotency-Replayed", String(replayed))
    return order
  }

  @Get()
  @UseGuards(AdminTokenGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: "Список заказов, новые сверху (админка)" })
  @ApiOkResponse({ type: OrderPage })
  list(@Query() query: ListOrdersQuery): Promise<OrderPage> {
    return this.orders.list(query)
  }

  @Get(":id")
  @UseGuards(AdminTokenGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: "Заказ по id (админка)" })
  @ApiOkResponse({ type: OrderView })
  get(@Param("id", ParseIntPipe) id: number): Promise<OrderView> {
    return this.orders.get(id)
  }

  @Patch(":id/status")
  @UseGuards(AdminTokenGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: "Сменить статус по разрешённому переходу (админка); недопустимый переход — 409" })
  @ApiOkResponse({ type: OrderView })
  changeStatus(@Param("id", ParseIntPipe) id: number, @Body() dto: ChangeStatusDto): Promise<OrderView> {
    return this.orders.changeStatus(id, dto)
  }
}
