import { createSelector, createSlice, nanoid, type PayloadAction } from '@reduxjs/toolkit'
import type { CreateOrderBody } from '../../api/types'

export type DraftLine = { sku: string; title: string; unitPriceKopecks: number; quantity: number }

export type OrderDraftState = {
  carId: number | null
  lines: DraftLine[]
  customer: { name: string; phone: string; city: string }
  /**
   * Ключ идемпотентности текущей попытки. Появляется при первой отправке и живёт,
   * пока форма не изменилась: повтор после сетевой ошибки уходит с тем же ключом,
   * и сервер вернёт уже созданный заказ, а не создаст второй.
   */
  idempotencyKey: string | null
}

const initialState: OrderDraftState = {
  carId: null,
  lines: [],
  customer: { name: '', phone: '', city: '' },
  idempotencyKey: null,
}

export const MAX_QUANTITY = 99

function generateKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `ord-${nanoid(24)}`
}

export const orderDraftSlice = createSlice({
  name: 'orderDraft',
  initialState,
  reducers: {
    carSelected(state, action: PayloadAction<number | null>) {
      state.carId = action.payload
    },
    lineAdded(state, action: PayloadAction<Omit<DraftLine, 'quantity'>>) {
      const existing = state.lines.find((l) => l.sku === action.payload.sku)
      if (existing) existing.quantity = Math.min(MAX_QUANTITY, existing.quantity + 1)
      else state.lines.push({ ...action.payload, quantity: 1 })
      state.idempotencyKey = null
    },
    quantityChanged(state, action: PayloadAction<{ sku: string; quantity: number }>) {
      const line = state.lines.find((l) => l.sku === action.payload.sku)
      if (!line) return
      line.quantity = Number.isFinite(action.payload.quantity) ? Math.trunc(action.payload.quantity) : 0
      state.idempotencyKey = null
    },
    lineRemoved(state, action: PayloadAction<string>) {
      state.lines = state.lines.filter((l) => l.sku !== action.payload)
      state.idempotencyKey = null
    },
    customerChanged(state, action: PayloadAction<Partial<OrderDraftState['customer']>>) {
      state.customer = { ...state.customer, ...action.payload }
      state.idempotencyKey = null
    },
    /** Начало попытки отправки: ключ создаётся один раз и переиспользуется до изменения формы. */
    submitAttempted: {
      reducer(state, action: PayloadAction<string>) {
        state.idempotencyKey ??= action.payload
      },
      prepare: () => ({ payload: generateKey() }),
    },
    draftReset: () => initialState,
  },
  selectors: {
    selectDraft: (state) => state,
    selectIdempotencyKey: (state) => state.idempotencyKey,
  },
})

export const { carSelected, lineAdded, quantityChanged, lineRemoved, customerChanged, submitAttempted, draftReset } =
  orderDraftSlice.actions
export const { selectDraft, selectIdempotencyKey } = orderDraftSlice.selectors

export const selectDraftTotalKopecks = createSelector([selectDraft], (d) =>
  d.lines.reduce((sum, l) => sum + l.unitPriceKopecks * Math.max(0, l.quantity), 0),
)

/** Тело POST /orders. Пустой город не отправляем; цены не отправляем — их считает сервер. */
export const selectCreateOrderBody = createSelector([selectDraft], (d): CreateOrderBody => {
  const city = d.customer.city.trim()
  return {
    customer: { name: d.customer.name.trim(), phone: d.customer.phone.trim(), ...(city ? { city } : {}) },
    items: d.lines.map((l) => ({ sku: l.sku, quantity: l.quantity })),
  }
})
