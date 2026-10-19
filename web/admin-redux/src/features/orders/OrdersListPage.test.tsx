import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { apiError, makeOrder } from '../../test/fixtures'
import { renderApp, TEST_TOKEN } from '../../test/render'
import { server, url } from '../../test/server'
import { plain } from '../../test/text'


/** Сервер-заглушка: 45 заказов, фильтр и пагинация как у настоящего API; запоминает запросы. */
function mockOrders() {
  const all = Array.from({ length: 45 }, (_, i) => makeOrder(45 - i, i % 3 === 0 ? 'confirmed' : 'new'))
  const requests: { status: string | null; page: string | null; limit: string | null; auth: string | null }[] = []
  server.use(
    http.get(url('/orders'), ({ request }) => {
      const sp = new URL(request.url).searchParams
      requests.push({ status: sp.get('status'), page: sp.get('page'), limit: sp.get('limit'), auth: request.headers.get('Authorization') })
      const status = sp.get('status')
      const page = Number(sp.get('page'))
      const limit = Number(sp.get('limit'))
      const filtered = status ? all.filter((o) => o.status === status) : all
      return HttpResponse.json({ items: filtered.slice((page - 1) * limit, page * limit), total: filtered.length, page, limit })
    }),
  )
  return requests
}

describe('OrdersListPage', () => {
  it('грузит список с токеном, показывает суммы в рублях и статусы', async () => {
    const requests = mockOrders()
    renderApp('/orders')

    expect(screen.getByRole('status')).toHaveTextContent('Загружаем заказы')
    const rows = await screen.findAllByRole('row')
    expect(rows).toHaveLength(21) // заголовок + 20
    const first = rows[1]
    if (!first) throw new Error('нет строки')
    expect(within(first).getByRole('link', { name: '45' })).toHaveAttribute('href', '/orders/45')
    expect(plain(first.textContent)).toContain('35 500 ₽')
    expect(within(first).getByText('Подтверждён')).toBeInTheDocument()
    expect(screen.getByText('Страница 1 из 3')).toBeInTheDocument()
    expect(requests[0]).toEqual({ status: null, page: '1', limit: '20', auth: `Bearer ${TEST_TOKEN}` })
  })

  it('вкладка статуса и пагинация идут через ui-slice и меняют запрос', async () => {
    const requests = mockOrders()
    const user = userEvent.setup()
    const { store } = renderApp('/orders')
    await screen.findByText('Страница 1 из 3')

    await user.click(screen.getByRole('button', { name: 'Вперёд →' }))
    await screen.findByText('Страница 2 из 3')
    expect(store.getState().ui.ordersFilter.page).toBe(2)

    await user.click(screen.getByRole('tab', { name: 'Новый' }))
    expect(screen.getByRole('tab', { name: 'Новый' })).toHaveAttribute('aria-selected', 'true')
    await screen.findByText('Страница 1 из 2')
    expect(store.getState().ui.ordersFilter).toMatchObject({ status: 'new', page: 1 })
    expect(requests.at(-1)).toMatchObject({ status: 'new', page: '1' })
  })

  it('пустое состояние для статуса без заказов', async () => {
    server.use(http.get(url('/orders'), () => HttpResponse.json({ items: [], total: 0, page: 1, limit: 20 })))
    const user = userEvent.setup()
    renderApp('/orders')
    await screen.findByText('Заказов пока нет')
    await user.click(screen.getByRole('tab', { name: 'Доставлен' }))
    expect(await screen.findByText('Нет заказов со статусом «Доставлен»')).toBeInTheDocument()
  })

  it('ошибка сервера показывается единым сообщением с повтором', async () => {
    let calls = 0
    server.use(
      http.get(url('/orders'), () => {
        calls += 1
        return calls === 1
          ? HttpResponse.json(apiError(500, 'INTERNAL', 'Internal'), { status: 500 })
          : HttpResponse.json({ items: [makeOrder(1)], total: 1, page: 1, limit: 20 })
      }),
    )
    const user = userEvent.setup()
    renderApp('/orders')
    expect(await screen.findByRole('alert')).toHaveTextContent('Ошибка на сервере. Попробуйте позже.')
    await user.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('link', { name: '1' })).toBeInTheDocument()
  })

  it('401 — разлогин и экран входа с объяснением', async () => {
    server.use(http.get(url('/orders'), () => HttpResponse.json(apiError(401, 'UNAUTHORIZED', 'Нужен токен'), { status: 401 })))
    const { store } = renderApp('/orders')
    expect(await screen.findByText('Сервер не принял токен. Проверьте его и войдите снова.')).toBeInTheDocument()
    expect(store.getState().auth).toEqual({ token: null, logoutReason: 'unauthorized' })
    expect(sessionStorage.length).toBe(0)
  })
})
