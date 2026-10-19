import { Controller, Get, Param, Query } from "@nestjs/common"
import { ApiOperation, ApiTags } from "@nestjs/swagger"
import { KitsQuery, PartsQuery } from "./catalog.dto.js"
import { CatalogService } from "./catalog.service.js"

@ApiTags("catalog")
@Controller("catalog")
export class CatalogController {
  constructor(private readonly catalog: CatalogService) {}

  @Get("parts")
  @ApiOperation({ summary: "Позиции каталога (без архивных), фильтр по типу и поиск" })
  parts(@Query() query: PartsQuery) {
    return this.catalog.listParts(query)
  }

  @Get("parts/:sku")
  @ApiOperation({ summary: "Позиция по артикулу" })
  part(@Param("sku") sku: string) {
    return this.catalog.getPart(sku)
  }

  @Get("cars")
  @ApiOperation({ summary: "Автомобили, под которые есть комплекты" })
  cars() {
    return this.catalog.listCars()
  }

  @Get("kits")
  @ApiOperation({ summary: "Комплекты, фильтр по автомобилю" })
  kits(@Query() query: KitsQuery) {
    return this.catalog.listKits(query)
  }

  @Get("kits/:sku")
  @ApiOperation({ summary: "Комплект с составом (артикул вида kit-12)" })
  kit(@Param("sku") sku: string) {
    return this.catalog.getKit(sku)
  }
}
