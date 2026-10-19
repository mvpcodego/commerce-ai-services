import { api } from './baseApi'
import type { CreateOrderBody, CreateOrderResult, ListOrdersArgs, Order, OrderStatus, Page } from './types'

const LIST = { type: 'Order', id: 'LIST' } as const

export const ordersApi = api.injectEndpoints({
  endpoints: (build) => ({
    listOrders: build.query<Page<Order>, ListOrdersArgs>({
      query: ({ status, page, limit }) => ({ url: '/orders', params: { ...(status ? { status } : {}), page, limit } }),
      providesTags: (result) => (result ? [...result.items.map((o) => ({ type: 'Order' as const, id: o.id })), LIST] : [LIST]),
    }),

    getOrder: build.query<Order, number>({
      query: (id) => `/orders/${id}`,
      providesTags: (_r, _e, id) => [{ type: 'Order', id }],
    }),

    changeOrderStatus: build.mutation<Order, { id: number; status: OrderStatus }>({
      query: ({ id, status }) => ({ url: `/orders/${id}/status`, method: 'PATCH', body: { status } }),
      /**
       * Оптимистично: статус в карточке и во всех закэшированных страницах списка меняется сразу.
       * Пока сервер не ответил, переходы неизвестны — кнопки скрыты (allowedTransitions = []).
       * Ошибка (409 — заказ уже поменял кто-то другой) → откат патчей и перезапрос заказа.
       */
      async onQueryStarted({ id, status }, lifecycle) {
        const { dispatch, queryFulfilled } = lifecycle
        const patches = [
          dispatch(
            ordersApi.util.updateQueryData('getOrder', id, (draft) => {
              draft.status = status
              draft.allowedTransitions = []
            }),
          ),
        ]
        for (const { endpointName, originalArgs } of ordersApi.util.selectInvalidatedBy(lifecycle.getState(), [{ type: 'Order', id }])) {
          if (endpointName !== 'listOrders') continue
          patches.push(
            dispatch(
              ordersApi.util.updateQueryData('listOrders', originalArgs as ListOrdersArgs, (draft) => {
                const row = draft.items.find((o) => o.id === id)
                if (row) {
                  row.status = status
                  row.allowedTransitions = []
                }
              }),
            ),
          )
        }
        try {
          const { data } = await queryFulfilled
          // Ответ сервера — источник правды: кладём его в карточку без лишнего запроса.
          void dispatch(ordersApi.util.upsertQueryData('getOrder', id, data))
        } catch {
          for (const p of patches) p.undo()
        }
      },
      // Успех: списки с фильтром по статусу устарели. Ошибка: заказ мог измениться — перечитать его.
      invalidatesTags: (_r, error, { id }) => (error ? [{ type: 'Order', id }] : [LIST]),
    }),

    createOrder: build.mutation<CreateOrderResult, { body: CreateOrderBody; idempotencyKey: string }>({
      query: ({ body, idempotencyKey }) => ({
        url: '/orders',
        method: 'POST',
        body,
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
      transformResponse: (order: Order, meta) => ({
        order,
        replayed: meta?.response?.headers.get('Idempotency-Replayed') === 'true',
      }),
      invalidatesTags: (result) => (result ? [LIST] : []),
    }),
  }),
})

export const { useListOrdersQuery, useGetOrderQuery, useChangeOrderStatusMutation, useCreateOrderMutation } = ordersApi
