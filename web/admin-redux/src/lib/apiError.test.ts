import { describe, expect, it } from 'vitest'
import { apiError } from '../test/fixtures'
import { formatApiError } from './apiError'

describe('formatApiError', () => {
  it('409 INVALID_TRANSITION — по-русски, со статусами и тем, что можно сейчас', () => {
    const e = formatApiError({
      status: 409,
      data: apiError(409, 'INVALID_TRANSITION', 'Нельзя…', { from: 'cancelled', to: 'confirmed', allowed: [] }),
    })
    expect(e.code).toBe('INVALID_TRANSITION')
    expect(e.httpStatus).toBe(409)
    expect(e.message).toBe('Статус не изменён: заказ уже «Отменён», перевести в «Подтверждён» нельзя. Сейчас можно: никуда.')
  })

  it('VALIDATION_FAILED — ошибки по полям, известные поля с русской подсказкой', () => {
    const e = formatApiError({
      status: 400,
      data: apiError(400, 'VALIDATION_FAILED', 'Запрос не прошёл проверку', [
        { field: 'customer.phone', errors: ['phone: нужен российский номер из 11 цифр'] },
        { field: 'items.1.quantity', errors: ['quantity must not be greater than 99'] },
        { field: 'something.else', errors: ['raw message'] },
      ]),
    })
    expect(e.message).toBe('Проверьте поля формы')
    expect(e.fieldErrors).toEqual({
      'customer.phone': ['Телефон: российский номер из 11 цифр'],
      'items.1.quantity': ['Количество: от 1 до 99'],
      'something.else': ['raw message'],
    })
  })

  it('UNKNOWN_SKU перечисляет артикулы', () => {
    const e = formatApiError({ status: 422, data: apiError(422, 'UNKNOWN_SKU', 'x', { skus: ['A-1', 'B-2'] }) })
    expect(e.message).toBe('Нет в каталоге или снято с продажи: A-1, B-2')
  })

  it('неизвестный код — сообщение сервера как есть', () => {
    const e = formatApiError({ status: 404, data: apiError(404, 'ORDER_NOT_FOUND', 'Заказ 9 не найден') })
    expect(e).toMatchObject({ code: 'ORDER_NOT_FOUND', message: 'Заказ 9 не найден', fieldErrors: {} })
  })

  it('сетевые ошибки и ответ не в формате API', () => {
    expect(formatApiError({ status: 'FETCH_ERROR', error: 'TypeError: Failed to fetch' }).message).toMatch(/Сервер недоступен/)
    expect(formatApiError({ status: 502, data: '<html>Bad gateway</html>' })).toMatchObject({ code: 'HTTP_502', httpStatus: 502 })
    expect(formatApiError({ status: 'PARSING_ERROR', originalStatus: 200, data: 'x', error: 'bad json' }).code).toBe('PARSING_ERROR')
  })

  it('SerializedError и пустое значение', () => {
    expect(formatApiError({ message: 'boom', name: 'Error' }).message).toBe('boom')
    expect(formatApiError(undefined).code).toBe('UNKNOWN')
  })
})
