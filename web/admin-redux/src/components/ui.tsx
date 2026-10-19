import type { SerializedError } from '@reduxjs/toolkit'
import type { FetchBaseQueryError } from '@reduxjs/toolkit/query'
import type { ReactNode } from 'react'
import type { OrderStatus } from '../api/types'
import { STATUS_LABEL } from '../features/orders/statusLabels'
import { formatApiError } from '../lib/apiError'
import s from './ui.module.css'

export function StatusBadge({ status }: { status: OrderStatus }) {
  return <span className={`${s.badge} ${s[status]}`}>{STATUS_LABEL[status]}</span>
}

export function ErrorBanner({ error, onRetry }: { error: FetchBaseQueryError | SerializedError | undefined; onRetry?: () => void }) {
  if (!error) return null
  return (
    <div role="alert" className={s.error}>
      {formatApiError(error).message}
      {onRetry && (
        <>
          {' '}
          <button type="button" className={s.button} onClick={onRetry}>
            Повторить
          </button>
        </>
      )}
    </div>
  )
}

export function Loading({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className={s.state} role="status">
      {label}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className={s.state}>{children}</div>
}

export function FieldError({ messages, id }: { messages: string[] | undefined; id?: string }) {
  if (!messages?.length) return null
  return (
    <p className={s.fieldError} id={id}>
      {messages.join('. ')}
    </p>
  )
}
