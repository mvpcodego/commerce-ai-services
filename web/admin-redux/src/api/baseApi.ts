import { createApi, fetchBaseQuery, type BaseQueryFn, type FetchArgs, type FetchBaseQueryError, type FetchBaseQueryMeta } from '@reduxjs/toolkit/query/react'
import { loggedOut } from '../features/auth/authSlice'
import { API_URL } from '../lib/config'

const rawBaseQuery = fetchBaseQuery({
  baseUrl: API_URL,
  prepareHeaders: (headers, { getState }) => {
    // getState без типа RootState — чтобы не было цикла импортов store ↔ api.
    const token = (getState() as { auth?: { token?: string | null } }).auth?.token
    if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)
    return headers
  },
})

/** 401 от любого админского маршрута = токен неверный или отозван → разлогин. */
const baseQueryWithLogout: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError, object, FetchBaseQueryMeta> = async (args, api, extra) => {
  const result = await rawBaseQuery(args, api, extra)
  if (result.error?.status === 401) api.dispatch(loggedOut('unauthorized'))
  return result
}

export const api = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithLogout,
  tagTypes: ['Order'],
  endpoints: () => ({}),
})
