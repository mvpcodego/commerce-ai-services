import { describe, expect, it } from 'vitest'
import { makeStore } from '../../app/store'
import {
  customerChanged,
  draftReset,
  lineAdded,
  lineRemoved,
  quantityChanged,
  selectCreateOrderBody,
  selectDraftTotalKopecks,
  selectIdempotencyKey,
  submitAttempted,
} from './orderDraftSlice'

const kit = { sku: 'kit-47', title: 'Solaris', unitPriceKopecks: 3550000 }
const cam = { sku: 'CAM-01', title: 'Камера', unitPriceKopecks: 199050 }

describe('orderDraftSlice', () => {
  it('повторное добавление того же артикула увеличивает количество, а не дублирует строку', () => {
    const store = makeStore()
    store.dispatch(lineAdded(kit))
    store.dispatch(lineAdded(kit))
    expect(store.getState().orderDraft.lines).toEqual([{ ...kit, quantity: 2 }])
  })

  it('итог в копейках по строкам', () => {
    const store = makeStore()
    store.dispatch(lineAdded(kit))
    store.dispatch(lineAdded(cam))
    store.dispatch(quantityChanged({ sku: 'CAM-01', quantity: 3 }))
    expect(selectDraftTotalKopecks(store.getState())).toBe(3550000 + 3 * 199050)
  })

  it('тело запроса: без цен, пустой город не отправляется, имя обрезано', () => {
    const store = makeStore()
    store.dispatch(lineAdded(kit))
    store.dispatch(customerChanged({ name: '  Иван  ', phone: '+7 900 000-00-01', city: '  ' }))
    expect(selectCreateOrderBody(store.getState())).toEqual({
      customer: { name: 'Иван', phone: '+7 900 000-00-01' },
      items: [{ sku: 'kit-47', quantity: 1 }],
    })
  })

  describe('ключ идемпотентности', () => {
    it('создаётся при первой попытке и не меняется при повторе той же формы', () => {
      const store = makeStore()
      store.dispatch(lineAdded(kit))
      expect(selectIdempotencyKey(store.getState())).toBeNull()
      store.dispatch(submitAttempted())
      const first = selectIdempotencyKey(store.getState())
      expect(first).toMatch(/^[0-9a-f-]{36}$/)
      store.dispatch(submitAttempted())
      store.dispatch(submitAttempted())
      expect(selectIdempotencyKey(store.getState())).toBe(first)
    })

    it.each([
      ['изменение клиента', customerChanged({ phone: '79000000002' })],
      ['количество', quantityChanged({ sku: 'kit-47', quantity: 2 })],
      ['новая строка', lineAdded(cam)],
      ['удаление строки', lineRemoved('kit-47')],
    ])('сбрасывается, если форма изменилась: %s', (_name, action) => {
      const store = makeStore()
      store.dispatch(lineAdded(kit))
      store.dispatch(submitAttempted())
      const first = selectIdempotencyKey(store.getState())
      store.dispatch(action)
      expect(selectIdempotencyKey(store.getState())).toBeNull()
      store.dispatch(submitAttempted())
      expect(selectIdempotencyKey(store.getState())).not.toBe(first)
    })

    it('draftReset очищает всё', () => {
      const store = makeStore()
      store.dispatch(lineAdded(kit))
      store.dispatch(submitAttempted())
      store.dispatch(draftReset())
      expect(store.getState().orderDraft).toEqual({ carId: null, lines: [], customer: { name: '', phone: '', city: '' }, idempotencyKey: null })
    })
  })
})
