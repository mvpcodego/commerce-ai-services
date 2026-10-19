import { describe, expect, it } from 'vitest'
import { ordersApi } from '../../api/ordersApi'
import { makeStore } from '../../app/store'
import { authSlice, loggedIn, loggedOut, selectIsAuthenticated, selectLogoutReason, selectToken } from './authSlice'
import { readToken } from './tokenStorage'

describe('authSlice', () => {
  it('вход обрезает пробелы и снимает причину выхода', () => {
    const s = authSlice.reducer({ token: null, logoutReason: 'unauthorized' }, loggedIn('  abc  '))
    expect(s).toEqual({ token: 'abc', logoutReason: null })
  })

  it('выход очищает токен и запоминает причину', () => {
    expect(authSlice.reducer({ token: 'abc', logoutReason: null }, loggedOut('unauthorized'))).toEqual({
      token: null,
      logoutReason: 'unauthorized',
    })
  })

  it('селекторы на корневом состоянии', () => {
    const store = makeStore()
    expect(selectIsAuthenticated(store.getState())).toBe(false)
    store.dispatch(loggedIn('tok'))
    expect(selectToken(store.getState())).toBe('tok')
    store.dispatch(loggedOut('manual'))
    expect(selectLogoutReason(store.getState())).toBe('manual')
  })

  it('listener: токен пишется в sessionStorage, при выходе — стирается вместе с кэшем API', () => {
    const store = makeStore()
    store.dispatch(loggedIn('secret-token'))
    expect(readToken()).toBe('secret-token')

    // в кэше лежат данные заказа — после выхода их не должно остаться
    void store.dispatch(ordersApi.util.upsertQueryData('getOrder', 1, { id: 1 } as never))
    expect(Object.keys(store.getState().api.queries)).not.toHaveLength(0)

    store.dispatch(loggedOut('manual'))
    expect(readToken()).toBeNull()
    expect(store.getState().api.queries).toEqual({})
  })
})
