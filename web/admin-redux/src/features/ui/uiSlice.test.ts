import { describe, expect, it } from 'vitest'
import { makeStore } from '../../app/store'
import { pageChanged, pageSizeChanged, selectOrdersQueryArgs, statusFilterChanged, totalPages, uiSlice } from './uiSlice'

const reducer = uiSlice.reducer
const initial = reducer(undefined, { type: '@@init' })

describe('uiSlice', () => {
  it('начальное состояние: все статусы, первая страница по 20', () => {
    expect(initial.ordersFilter).toEqual({ status: 'all', page: 1, limit: 20 })
  })

  it('смена статуса сбрасывает страницу, тот же статус — нет', () => {
    const onPage3 = reducer(initial, pageChanged(3))
    expect(reducer(onPage3, statusFilterChanged('shipped')).ordersFilter).toEqual({ status: 'shipped', page: 1, limit: 20 })
    expect(reducer(onPage3, statusFilterChanged('all')).ordersFilter.page).toBe(3)
  })

  it('страница не меньше 1, размер страницы в пределах 1..100 и сбрасывает страницу', () => {
    expect(reducer(initial, pageChanged(0)).ordersFilter.page).toBe(1)
    const s = reducer(reducer(initial, pageChanged(4)), pageSizeChanged(500))
    expect(s.ordersFilter).toMatchObject({ page: 1, limit: 100 })
  })

  it('totalPages', () => {
    expect(totalPages(0, 20)).toBe(1)
    expect(totalPages(41, 20)).toBe(3)
  })
})

describe('selectOrdersQueryArgs', () => {
  it('без статуса для «Все», со статусом для вкладки', () => {
    const store = makeStore()
    expect(selectOrdersQueryArgs(store.getState())).toEqual({ page: 1, limit: 20 })
    store.dispatch(statusFilterChanged('new'))
    expect(selectOrdersQueryArgs(store.getState())).toEqual({ status: 'new', page: 1, limit: 20 })
  })

  it('мемоизирован: без изменений фильтра возвращает тот же объект', () => {
    const store = makeStore()
    const a = selectOrdersQueryArgs(store.getState())
    store.dispatch({ type: 'unrelated' })
    expect(selectOrdersQueryArgs(store.getState())).toBe(a)
  })
})
