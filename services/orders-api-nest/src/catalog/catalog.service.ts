import { Injectable } from "@nestjs/common"
import { InjectDataSource } from "@nestjs/typeorm"
import { DataSource, EntityManager, ILike, In } from "typeorm"
import { DomainError } from "../common/domain-error.js"
import type { Page } from "../common/pagination.js"
import { Car, Kit, Part } from "./catalog.entities.js"
import type { KitsQuery, PartsQuery } from "./catalog.dto.js"

export type Sellable = { sku: string; title: string; priceKopecks: number }

@Injectable()
export class CatalogService {
  constructor(@InjectDataSource() private readonly ds: DataSource) {}

  async listParts(query: PartsQuery): Promise<Page<Part>> {
    const repo = this.ds.getRepository(Part)
    const base = { archived: false, ...(query.type ? { type: query.type } : {}) }
    const q = query.q?.trim()
    // ILike — значение параметризовано; % и _ из ввода экранируем, чтобы поиск был по подстроке как есть.
    const pattern = q ? `%${q.replace(/[\\%_]/g, (c) => `\\${c}`)}%` : undefined
    const where = pattern ? [{ ...base, title: ILike(pattern) }, { ...base, sku: ILike(pattern) }] : base
    const [items, total] = await repo.findAndCount({
      where,
      order: { id: "ASC" },
      skip: (query.page - 1) * query.limit,
      take: query.limit,
    })
    return { items, total, page: query.page, limit: query.limit }
  }

  async getPart(sku: string): Promise<Part> {
    const part = await this.ds.getRepository(Part).findOneBy({ sku })
    if (!part) throw new DomainError(404, "PART_NOT_FOUND", `Позиция ${sku} не найдена`)
    return part
  }

  listCars(): Promise<Car[]> {
    return this.ds.getRepository(Car).find({ order: { make: "ASC", model: "ASC" } })
  }

  async listKits(query: KitsQuery): Promise<Page<Kit>> {
    const [items, total] = await this.ds.getRepository(Kit).findAndCount({
      where: query.carId ? { carId: query.carId } : {},
      order: { id: "ASC" },
      skip: (query.page - 1) * query.limit,
      take: query.limit,
    })
    return { items, total, page: query.page, limit: query.limit }
  }

  async getKit(sku: string): Promise<{ kit: Kit; car: Car | null; components: Part[] }> {
    const kit = await this.ds.getRepository(Kit).findOneBy({ sku })
    if (!kit) throw new DomainError(404, "KIT_NOT_FOUND", `Комплект ${sku} не найден`)
    const ids = [kit.headUnitId, kit.frameId, kit.wiringId, kit.starterKitId].filter((id): id is number => id !== null)
    const [car, parts] = await Promise.all([
      this.ds.getRepository(Car).findOneBy({ id: kit.carId }),
      this.ds.getRepository(Part).findBy({ id: In(ids) }),
    ])
    return { kit, car, components: ids.map((id) => parts.find((p) => p.id === id)).filter((p): p is Part => !!p) }
  }

  /** Цены и названия для заказа берутся только из каталога — клиент цену не передаёт. */
  async resolveSellable(skus: string[], manager: EntityManager = this.ds.manager): Promise<Map<string, Sellable>> {
    const [parts, kits] = await Promise.all([
      manager.getRepository(Part).findBy({ sku: In(skus), archived: false }),
      manager.getRepository(Kit).findBy({ sku: In(skus) }),
    ])
    return new Map([...parts, ...kits].map((x) => [x.sku, { sku: x.sku, title: x.title, priceKopecks: x.priceKopecks }]))
  }
}
