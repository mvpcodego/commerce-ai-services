import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import type { CreateOrderBody } from '../../api/types'
import { apiError, makeOrder } from '../../test/fixtures'
import { renderApp } from '../../test/render'
import { server, url } from '../../test/server'
import { plain } from '../../test/text'

type Sent = { key: string | null; body: CreateOrderBody; auth: string | null }

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole('option', { name: /Hyundai Solaris/ })
  await user.selectOptions(screen.getByRole('combobox', { name: 'Автомобиль' }), '1')
  const kitsCard = screen.getByRole('region', { name: 'Комплект под автомобиль' })
  await user.click(await within(kitsCard).findByRole('button', { name: 'Добавить' }))
  await user.type(screen.getByRole('searchbox'), 'кам')
  const partsCard = screen.getByRole('region', { name: 'Позиции из каталога' })
  await user.click(await within(partsCard).findByRole('button', { name: 'Добавить' }, { timeout: 2000 }))
  await user.type(screen.getByRole('textbox', { name: 'Имя' }), 'Иван Петров')
  await user.type(screen.getByRole('textbox', { name: 'Телефон' }), '+7 900 000-00-01')
}

describe('NewOrderPage', () => {
  it('машина → комплект + позиция → клиент → заказ; итог считается в копейках', async () => {
    const sent: Sent[] = []
    server.use(
      http.post(url('/orders'), async ({ request }) => {
        sent.push({ key: request.headers.get('Idempotency-Key'), body: (await request.json()) as CreateOrderBody, auth: request.headers.get('Authorization') })
        return HttpResponse.json(makeOrder(500), { status: 201, headers: { 'Idempotency-Replayed': 'false' } })
      }),
      http.get(url('/orders/500'), () => HttpResponse.json(makeOrder(500))),
    )
    const user = userEvent.setup()
    const { store } = renderApp('/orders/new')
    await fillForm(user)

    expect(plain(screen.getByTestId('draft-total').textContent)).toBe('37 490 ₽')
    await user.click(screen.getByRole('button', { name: 'Оформить заказ' }))

    expect(await screen.findByText('Заказ создан')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Заказ № 500' })).toBeInTheDocument()
    expect(sent).toHaveLength(1)
    expect(sent[0]?.body).toEqual({
      customer: { name: 'Иван Петров', phone: '+7 900 000-00-01' },
      items: [
        { sku: 'kit-47', quantity: 1 },
        { sku: 'CAM-01', quantity: 1 },
      ],
    })
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/)
    expect(store.getState().orderDraft.lines).toHaveLength(0)
  })

  it('повтор той же формы после сбоя уходит с тем же ключом; изменение формы — новый ключ', async () => {
    const keys: (string | null)[] = []
    server.use(
      http.post(url('/orders'), ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'))
        return HttpResponse.json(apiError(500, 'INTERNAL', 'Internal'), { status: 500 })
      }),
    )
    const user = userEvent.setup()
    renderApp('/orders/new')
    await fillForm(user)

    const submit = screen.getByRole('button', { name: 'Оформить заказ' })
    await user.click(submit)
    expect(await screen.findByRole('alert')).toHaveTextContent('Ошибка на сервере')
    await user.click(submit)
    await vi.waitFor(() => {
      expect(keys).toHaveLength(2)
    })
    expect(keys[1]).toBe(keys[0])
    expect(screen.getByTestId('idempotency-key')).toHaveTextContent(`${keys[0]?.slice(0, 8) ?? ''}…`)

    await user.type(screen.getByRole('textbox', { name: /Город/ }), 'Тула')
    await user.click(submit)
    await vi.waitFor(() => {
      expect(keys).toHaveLength(3)
    })
    expect(keys[2]).not.toBe(keys[0])
  })

  it('ответ-повтор (Idempotency-Replayed: true) — сообщение, что второй заказ не создан', async () => {
    server.use(
      http.post(url('/orders'), () =>
        HttpResponse.json(makeOrder(501), { status: 201, headers: { 'Idempotency-Replayed': 'true' } }),
      ),
      http.get(url('/orders/501'), () => HttpResponse.json(makeOrder(501))),
    )
    const user = userEvent.setup()
    renderApp('/orders/new')
    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Оформить заказ' }))
    expect(await screen.findByText(/уже был создан ранее с тем же ключом/)).toBeInTheDocument()
  })

  it('400 VALIDATION_FAILED — ошибки под полями и у строки заказа', async () => {
    server.use(
      http.post(url('/orders'), () =>
        HttpResponse.json(
          apiError(400, 'VALIDATION_FAILED', 'Запрос не прошёл проверку', [
            { field: 'customer.phone', errors: ['phone: нужен российский номер из 11 цифр'] },
            { field: 'customer.name', errors: ['name must be longer than or equal to 2 characters'] },
            { field: 'items.1.quantity', errors: ['quantity must not be greater than 99'] },
          ]),
          { status: 400 },
        ),
      ),
    )
    const user = userEvent.setup()
    renderApp('/orders/new')
    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Оформить заказ' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Проверьте поля формы')
    expect(screen.getByText('Телефон: российский номер из 11 цифр')).toBeInTheDocument()
    expect(screen.getByText('Имя: от 2 до 100 символов')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Телефон' })).toHaveAttribute('aria-invalid', 'true')
    const camLine = screen.getByRole('spinbutton', { name: 'Количество: Камера заднего вида' }).closest('li')
    expect(within(camLine as HTMLElement).getByText('Количество: от 1 до 99')).toBeInTheDocument()
  })

  it('422 UNKNOWN_SKU — список артикулов', async () => {
    server.use(
      http.post(url('/orders'), () =>
        HttpResponse.json(apiError(422, 'UNKNOWN_SKU', 'x', { skus: ['CAM-01'] }), { status: 422 }),
      ),
    )
    const user = userEvent.setup()
    renderApp('/orders/new')
    await fillForm(user)
    await user.click(screen.getByRole('button', { name: 'Оформить заказ' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Нет в каталоге или снято с продажи: CAM-01')
  })
})
