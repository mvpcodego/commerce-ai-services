import { combineSlices, configureStore, createListenerMiddleware, type Action, type ThunkAction } from '@reduxjs/toolkit'
import { setupListeners } from '@reduxjs/toolkit/query'
import { api } from '../api/baseApi'
import { authSlice, loggedIn, loggedOut } from '../features/auth/authSlice'
import { readToken, writeToken } from '../features/auth/tokenStorage'
import { orderDraftSlice } from '../features/new-order/orderDraftSlice'
import { uiSlice } from '../features/ui/uiSlice'

const rootReducer = combineSlices(authSlice, uiSlice, orderDraftSlice, api)
export type RootState = ReturnType<typeof rootReducer>

/** Побочные эффекты входа/выхода — вне редьюсеров: sessionStorage и сброс кэша чужих данных. */
function createAuthListener() {
  const listener = createListenerMiddleware()
  listener.startListening({
    actionCreator: loggedIn,
    effect: (action) => {
      writeToken(action.payload.trim())
    },
  })
  listener.startListening({
    actionCreator: loggedOut,
    effect: (_action, { dispatch }) => {
      writeToken(null)
      dispatch(api.util.resetApiState())
    },
  })
  return listener
}

export function makeStore(preloadedState?: Partial<RootState>) {
  const listener = createAuthListener()
  const store = configureStore({
    reducer: rootReducer,
    preloadedState,
    middleware: (getDefault) => getDefault().prepend(listener.middleware).concat(api.middleware),
  })
  setupListeners(store.dispatch)
  return store
}

export function initialStateFromStorage(): Partial<RootState> {
  const token = readToken()
  return token ? { auth: { token, logoutReason: null } } : {}
}

export type AppStore = ReturnType<typeof makeStore>
export type AppDispatch = AppStore['dispatch']
export type AppThunk<R = void> = ThunkAction<R, RootState, unknown, Action>
