import type { SerializedError } from '@reduxjs/toolkit'
import type { FetchBaseQueryError } from '@reduxjs/toolkit/query'
import type { ApiErrorBody, OrderStatus } from '../api/types'
import { STATUS_LABEL } from '../features/orders/statusLabels'

export type FormattedApiError = {
  /** Текст для человека. */
  message: string
  /** Машинный код API (`INVALID_TRANSITION`) или тип сетевой ошибки (`FETCH_ERROR`). */
  code: string
  httpStatus?: number
  /** Ошибки по полям для VALIDATION_FAILED: `customer.phone` → ['…']. */
  fieldErrors: Record<string, string[]>
}

const FIELD_HINTS: Record<string, string> = {
  'customer.name': 'Имя: от 2 до 100 символов',
  'customer.phone': 'Телефон: российский номер из 11 цифр',
  'customer.city': 'Город: не длиннее 100 символов',
  items: 'Добавьте от 1 до 50 позиций без повторов',
}

function isApiErrorBody(data: unknown): data is ApiErrorBody {
  return typeof data === 'object' && data !== null && 'code' in data && 'message' in data
}

function isFetchBaseQueryError(error: unknown): error is FetchBaseQueryError {
  return typeof error === 'object' && error !== null && 'status' in error
}

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null
}

function statusLabel(x: unknown): string {
  if (typeof x !== 'string') return '?'
  return x in STATUS_LABEL ? STATUS_LABEL[x as OrderStatus] : x
}

function statusList(list: unknown): string {
  if (!Array.isArray(list) || list.length === 0) return 'никуда'
  return list.map((s) => `«${statusLabel(s)}»`).join(', ')
}

function fieldErrorsFrom(details: unknown): Record<string, string[]> {
  if (!Array.isArray(details)) return {}
  const out: Record<string, string[]> = {}
  for (const d of details) {
    if (!isRecord(d) || typeof d.field !== 'string') continue
    const hint = FIELD_HINTS[d.field] ?? (/^items\.\d+\.quantity$/.test(d.field) ? 'Количество: от 1 до 99' : undefined)
    const raw = Array.isArray(d.errors) ? d.errors.map(String) : []
    out[d.field] = hint ? [hint] : raw
  }
  return out
}

function fromApiBody(body: ApiErrorBody, httpStatus: number): FormattedApiError {
  const base = { code: body.code, httpStatus, fieldErrors: {} }
  const details = body.details
  switch (body.code) {
    case 'INVALID_TRANSITION': {
      const d = isRecord(details) ? details : {}
      const from = statusLabel(d.from)
      const to = statusLabel(d.to)
      return {
        ...base,
        message: `Статус не изменён: заказ уже «${from}», перевести в «${to}» нельзя. Сейчас можно: ${statusList(d.allowed)}.`,
      }
    }
    case 'VALIDATION_FAILED':
      return { ...base, message: 'Проверьте поля формы', fieldErrors: fieldErrorsFrom(details) }
    case 'UNKNOWN_SKU': {
      const skus = isRecord(details) && Array.isArray(details.skus) ? details.skus.map(String) : []
      return {
        ...base,
        message: skus.length ? `Нет в каталоге или снято с продажи: ${skus.join(', ')}` : body.message,
      }
    }
    case 'IDEMPOTENCY_KEY_REUSED':
      return { ...base, message: 'Этот ключ уже использован для другого заказа. Обновите форму и отправьте ещё раз.' }
    case 'UNAUTHORIZED':
      return { ...base, message: 'Токен не принят. Войдите заново.' }
    case 'INTERNAL':
      return { ...base, message: 'Ошибка на сервере. Попробуйте позже.' }
    default:
      return { ...base, message: body.message }
  }
}

/** Любая ошибка RTK Query → сообщение для интерфейса. Один путь для всех экранов. */
export function formatApiError(error: FetchBaseQueryError | SerializedError | undefined | null): FormattedApiError {
  if (!error) return { message: 'Неизвестная ошибка', code: 'UNKNOWN', fieldErrors: {} }
  if (isFetchBaseQueryError(error)) {
    const { status } = error
    if (typeof status === 'number') {
      if (isApiErrorBody(error.data)) return fromApiBody(error.data, status)
      return { message: `Сервер ответил ${status}`, code: `HTTP_${status}`, httpStatus: status, fieldErrors: {} }
    }
    switch (status) {
      case 'FETCH_ERROR':
        return { message: 'Сервер недоступен. Проверьте, что API запущено.', code: status, fieldErrors: {} }
      case 'TIMEOUT_ERROR':
        return { message: 'Сервер не ответил вовремя', code: status, fieldErrors: {} }
      case 'PARSING_ERROR':
        return { message: `Непонятный ответ сервера (${error.originalStatus})`, code: status, httpStatus: error.originalStatus, fieldErrors: {} }
      default:
        return { message: error.error, code: status, fieldErrors: {} }
    }
  }
  return { message: error.message ?? 'Неизвестная ошибка', code: error.code ?? 'UNKNOWN', fieldErrors: {} }
}
