import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { API_URL } from '../lib/config'
import { cars, kits, parts } from './fixtures'

export const url = (path: string) => `${API_URL}${path}`

/** Каталог — общий для всех тестов; заказы каждый тест описывает сам через server.use. */
export const server = setupServer(
  http.get(url('/catalog/cars'), () => HttpResponse.json(cars)),
  http.get(url('/catalog/kits'), ({ request }) => {
    const carId = Number(new URL(request.url).searchParams.get('carId'))
    const items = kits.filter((k) => k.carId === carId)
    return HttpResponse.json({ items, total: items.length, page: 1, limit: 100 })
  }),
  http.get(url('/catalog/parts'), () => HttpResponse.json({ items: parts, total: parts.length, page: 1, limit: 20 })),
)
