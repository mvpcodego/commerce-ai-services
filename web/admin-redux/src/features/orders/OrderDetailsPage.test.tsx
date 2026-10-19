import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import { ordersApi } from '../../api/ordersApi'
import type { Order, OrderStatus } from '../../api/types'
import { apiError, makeOrder } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { server, url } from '../../test/server'
import { plain } from '../../test/text'


function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => (resolve = r))
  return { promise, resolve }
}

const badge = () => within(screen.getByRole('heading', { level: 1 }).parentElement as HTMLElement)

describe('OrderDetailsPage', () => {
  it('показывает состав, клиента, итог и кнопки по allowedTransitions', async () => {
    const order = makeOrder(7, 'new', {
      items: [
        { sku: 'kit-47', title: 'Комплект Solaris', unitPriceKopecks: 3550000, quantity: 1, lineTotalKopecks: 3550000 },
        { sku: 'CAM-01', title: 'Камера', unitPriceKopecks: 199050, quantity: 2, lineTotalKopecks: 398100 },
      ],
      totalKopecks: 3948100,
    })
    server.use(http.get(url('/orders/7'), () => HttpResponse.json(order)))
    renderApp('/orders/7')

    expect(await screen.findByRole('heading', { name: 'Заказ № 7' })).toBeInTheDocument()
    expect(plain(screen.getByTestId('order-total').textContent)).toBe('39 481 ₽')
    expect(screen.getByText('Камера')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '+7 900 000-00-01' })).toHaveAttribute('href', 'tel:+79000000001')
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Отменить заказ' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Отгрузить' })).not.toBeInTheDocument()
  })

  it('конечный статус — кнопок нет', async () => {
    server.use(http.get(url('/orders/8'), () => HttpResponse.json(makeOrder(8, 'delivered'))))
    renderApp('/orders/8')
    expect(await screen.findByText('Статус конечный, переходов нет')).toBeInTheDocument()
    expect(screen.queryAllByRole('button').filter((b) => b.textContent !== 'Выйти')).toHaveLength(0)
  })

  it('оптимистично меняет статус до ответа сервера и применяет ответ', async () => {
    let current: Order = makeOrder(9, 'new')
    const gate = deferred()
    server.use(
      http.get(url('/orders/9'), () => HttpResponse.json(current)),
      http.patch(url('/orders/9/status'), async ({ request }) => {
        const { status } = (await request.json()) as { status: OrderStatus }
        await gate.promise
        current = makeOrder(9, status)
        return HttpResponse.json(current)
      }),
    )
    const user = userEvent.setup()
    renderApp('/orders/9')
    await user.click(await screen.findByRole('button', { name: 'Подтвердить' }))

    // сервер ещё не ответил, а статус уже новый, кнопки скрыты
    expect(badge().getByText('Подтверждён')).toBeInTheDocument()
    expect(screen.getByText('Сохраняем…')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Подтвердить' })).not.toBeInTheDocument()

    gate.resolve()
    expect(await screen.findByRole('button', { name: 'Отгрузить' })).toBeInTheDocument()
    expect(badge().getByText('Подтверждён')).toBeInTheDocument()
  })

  it('409 — откат оптимистичного статуса, понятное сообщение и перечитанный заказ', async () => {
    const gate = deferred()
    let getCalls = 0
    server.use(
      http.get(url('/orders/10'), () => {
        getCalls += 1
        return HttpResponse.json(makeOrder(10, 'new'))
      }),
      http.patch(url('/orders/10/status'), async () => {
        await gate.promise
        return HttpResponse.json(
          apiError(409, 'INVALID_TRANSITION', 'Нельзя', { from: 'new', to: 'shipped', allowed: ['confirmed', 'cancelled'] }),
          { status: 409 },
        )
      }),
    )
    // Список уже в кэше: оптимистичный статус должен откатиться и в нём
    const list = { items: [makeOrder(10, 'new')], total: 1, page: 1, limit: 20 }
    server.use(http.get(url('/orders'), () => HttpResponse.json(list)))

    const user = userEvent.setup()
    const { store, router } = renderApp('/orders')
    await screen.findByRole('link', { name: '10' })
    // держим подписку на список, как если бы он был открыт в соседней панели
    const listSub = store.dispatch(ordersApi.endpoints.listOrders.initiate({ page: 1, limit: 20 }))
    await router.navigate('/orders/10')
    await user.click(await screen.findByRole('button', { name: 'Подтвердить' }))

    expect(badge().getByText('Подтверждён')).toBeInTheDocument()
    const cachedList = () => store.getState().api.queries['listOrders({"limit":20,"page":1})']?.data as typeof list | undefined
    expect(cachedList()?.items[0]?.status).toBe('confirmed')

    gate.resolve()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Статус не изменён: заказ уже «Новый», перевести в «Отправлен» нельзя. Сейчас можно: «Подтверждён», «Отменён».',
    )
    expect(badge().getByText('Новый')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeEnabled()
    expect(cachedList()?.items[0]?.status).toBe('new')
    // после 409 тег заказа инвалидирован — карточка перечитана с сервера
    await vi.waitFor(() => {
      expect(getCalls).toBe(2)
    })
    listSub.unsubscribe()
  })
})
