import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export type LogoutReason = 'manual' | 'unauthorized'

export type AuthState = { token: string | null; logoutReason: LogoutReason | null }

const initialState: AuthState = { token: null, logoutReason: null }

export const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loggedIn(state, action: PayloadAction<string>) {
      state.token = action.payload.trim()
      state.logoutReason = null
    },
    loggedOut(state, action: PayloadAction<LogoutReason>) {
      state.token = null
      state.logoutReason = action.payload
    },
  },
  selectors: {
    selectToken: (state) => state.token,
    selectIsAuthenticated: (state) => state.token !== null,
    selectLogoutReason: (state) => state.logoutReason,
  },
})

export const { loggedIn, loggedOut } = authSlice.actions
export const { selectToken, selectIsAuthenticated, selectLogoutReason } = authSlice.selectors
