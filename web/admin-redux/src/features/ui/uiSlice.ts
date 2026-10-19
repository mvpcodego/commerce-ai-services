import { createSelector, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { ListOrdersArgs, OrderStatus } from '../../api/types'

export type StatusFilter = OrderStatus | 'all'

export type UiState = { ordersFilter: { status: StatusFilter; page: number; limit: number } }

export const PAGE_SIZES = [10, 20, 50] as const

const initialState: UiState = { ordersFilter: { status: 'all', page: 1, limit: 20 } }

export const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    statusFilterChanged(state, action: PayloadAction<StatusFilter>) {
      if (state.ordersFilter.status === action.payload) return
      state.ordersFilter.status = action.payload
      state.ordersFilter.page = 1
    },
    pageChanged(state, action: PayloadAction<number>) {
      state.ordersFilter.page = Math.max(1, Math.trunc(action.payload))
    },
    pageSizeChanged(state, action: PayloadAction<number>) {
      state.ordersFilter.limit = Math.min(100, Math.max(1, Math.trunc(action.payload)))
      state.ordersFilter.page = 1
    },
  },
  selectors: {
    selectOrdersFilter: (state) => state.ordersFilter,
  },
})

export const { statusFilterChanged, pageChanged, pageSizeChanged } = uiSlice.actions
export const { selectOrdersFilter } = uiSlice.selectors

/** Аргументы запроса списка. Мемоизировано: тот же объект → RTK Query не пересоздаёт подписку. */
export const selectOrdersQueryArgs = createSelector([selectOrdersFilter], ({ status, page, limit }): ListOrdersArgs =>
  status === 'all' ? { page, limit } : { status, page, limit },
)

export function totalPages(total: number, limit: number): number {
  return Math.max(1, Math.ceil(total / limit))
}
