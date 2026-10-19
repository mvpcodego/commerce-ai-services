import { api } from './baseApi'
import type { Car, Kit, Page, Part } from './types'

// Каталог публичный и меняется редко — держим в кэше дольше обычного.
export const catalogApi = api.injectEndpoints({
  endpoints: (build) => ({
    listCars: build.query<Car[], undefined>({ query: () => '/catalog/cars', keepUnusedDataFor: 600 }),
    listKits: build.query<Page<Kit>, number>({
      query: (carId) => ({ url: '/catalog/kits', params: { carId, limit: 100 } }),
      keepUnusedDataFor: 600,
    }),
    searchParts: build.query<Page<Part>, string>({
      query: (q) => ({ url: '/catalog/parts', params: { q, limit: 20 } }),
    }),
  }),
})

export const { useListCarsQuery, useListKitsQuery, useSearchPartsQuery } = catalogApi
