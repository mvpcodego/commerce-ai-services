import { ApiPropertyOptional } from "@nestjs/swagger"
import { Type } from "class-transformer"
import { IsIn, IsInt, IsOptional, IsString, MaxLength, Min } from "class-validator"
import { PageQuery } from "../common/pagination.js"

export const PART_TYPES = [
  "head_unit", "frame", "wiring", "starter_kit", "camera", "door_closer",
  "tuning", "audio", "accessory", "alarm", "soundproofing", "adapter",
] as const

export class PartsQuery extends PageQuery {
  @ApiPropertyOptional({ enum: PART_TYPES })
  @IsOptional()
  @IsIn(PART_TYPES)
  type?: string

  @ApiPropertyOptional({ description: "Поиск по названию и артикулу" })
  @IsOptional()
  @IsString()
  @MaxLength(100)
  q?: string
}

export class KitsQuery extends PageQuery {
  @ApiPropertyOptional()
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  carId?: number
}
