import { Column, Entity, PrimaryColumn } from "typeorm"

@Entity({ name: "cars" })
export class Car {
  @PrimaryColumn("int") id: number
  @Column("text") make: string
  @Column("text") model: string
  @Column("text", { nullable: true }) generation: string | null
  @Column("int", { name: "year_from", nullable: true }) yearFrom: number | null
  @Column("int", { name: "year_to", nullable: true }) yearTo: number | null
  @Column("text", { unique: true }) slug: string
}

@Entity({ name: "parts" })
export class Part {
  @PrimaryColumn("int") id: number
  @Column("text", { unique: true }) sku: string
  @Column("text") type: string
  @Column("text") title: string
  @Column("text", { nullable: true }) brand: string | null
  @Column("jsonb", { default: {} }) specs: Record<string, unknown>
  @Column("int", { name: "price_kopecks" }) priceKopecks: number
  @Column("int") stock: number
  @Column("boolean") archived: boolean
  @Column("text", { name: "image_url", nullable: true }) imageUrl: string | null
}

/** Комплект «машина + магнитола + рамка + проводка + набор». В заказах артикул вида kit-<id>. */
@Entity({ name: "kits" })
export class Kit {
  @PrimaryColumn("int") id: number
  @Column("text", { unique: true }) sku: string
  @Column("int", { name: "car_id" }) carId: number
  @Column("int", { name: "head_unit_id" }) headUnitId: number
  @Column("int", { name: "frame_id" }) frameId: number
  @Column("int", { name: "wiring_id" }) wiringId: number
  @Column("int", { name: "starter_kit_id", nullable: true }) starterKitId: number | null
  @Column("text") title: string
  @Column("int", { name: "price_kopecks" }) priceKopecks: number
  @Column("boolean", { name: "is_default" }) isDefault: boolean
}
