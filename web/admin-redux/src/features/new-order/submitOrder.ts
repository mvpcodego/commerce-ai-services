import { ordersApi } from '../../api/ordersApi'
import type { AppThunk } from '../../app/store'
import { selectCreateOrderBody, selectIdempotencyKey, submitAttempted } from './orderDraftSlice'

export const CREATE_ORDER_KEY = 'create-order'

/**
 * Отправка черновика. Ключ берётся из стора: первая попытка его создаёт, повтор той же формы
 * (после таймаута, 5xx, двойного клика) отправляет тот же ключ, и сервер вернёт тот же заказ.
 */
export const submitOrder = (): AppThunk<ReturnType<ReturnType<typeof ordersApi.endpoints.createOrder.initiate>>> => (dispatch, getState) => {
  dispatch(submitAttempted())
  const state = getState()
  const idempotencyKey = selectIdempotencyKey(state)
  if (!idempotencyKey) throw new Error('Ключ идемпотентности не создан')
  return dispatch(
    ordersApi.endpoints.createOrder.initiate({ body: selectCreateOrderBody(state), idempotencyKey }, { fixedCacheKey: CREATE_ORDER_KEY }),
  )
}
