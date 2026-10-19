import { Link, useLocation, useParams } from 'react-router'
import { useChangeOrderStatusMutation, useGetOrderQuery } from '../../api/ordersApi'
import type { OrderStatus } from '../../api/types'
import { ErrorBanner, Loading, StatusBadge } from '../../components/ui'
import cls from '../../components/ui.module.css'
import { formatApiError } from '../../lib/apiError'
import { formatDateTime } from '../../lib/date'
import { formatKopecks } from '../../lib/money'
import { formatPhone } from '../../lib/phone'
import s from './OrderDetailsPage.module.css'
import { TRANSITION_ACTION } from './statusLabels'

export function OrderDetailsPage() {
  const id = Number(useParams().id)
  const valid = Number.isInteger(id) && id > 0
  const location = useLocation()
  const created = (location.state as { created?: 'new' | 'replayed' } | null)?.created
  const { data: order, error, isLoading, refetch } = useGetOrderQuery(id, { skip: !valid })
  const [changeStatus, { isLoading: isChanging, error: changeError, reset }] = useChangeOrderStatusMutation()

  if (!valid) return <div className={cls.error}>Некорректный номер заказа</div>
  if (isLoading) return <Loading label="Загружаем заказ…" />
  if (!order) return <ErrorBanner error={error} onRetry={() => void refetch()} />

  function transition(to: OrderStatus) {
    reset()
    void changeStatus({ id, status: to })
  }

  const isTerminal = !isChanging && order.allowedTransitions.length === 0

  return (
    <section className={s.page}>
      <Link to="/orders" className={s.back}>
        ← Все заказы
      </Link>

      <div className={s.head}>
        <h1>Заказ № {order.id}</h1>
        <StatusBadge status={order.status} />
      </div>
      <p className={s.meta}>
        Создан {formatDateTime(order.createdAt)} · изменён {formatDateTime(order.updatedAt)}
      </p>

      {created === 'new' && <div className={cls.notice}>Заказ создан</div>}
      {created === 'replayed' && (
        <div className={cls.notice}>Этот заказ уже был создан ранее с тем же ключом — второй не появился</div>
      )}
      {changeError && (
        <div role="alert" className={cls.error}>
          {formatApiError(changeError).message}
        </div>
      )}

      <div className={s.actions} aria-label="Сменить статус">
        {order.allowedTransitions.map((to) => (
          <button
            key={to}
            type="button"
            className={`${cls.button} ${to === 'cancelled' ? cls.danger : cls.primary}`}
            disabled={isChanging}
            onClick={() => {
              transition(to)
            }}
          >
            {TRANSITION_ACTION[to]}
          </button>
        ))}
        {isChanging && <span className={s.muted}>Сохраняем…</span>}
        {isTerminal && <span className={s.muted}>Статус конечный, переходов нет</span>}
      </div>

      <div className={s.grid}>
        <div className={cls.card}>
          <h2 className={s.h2}>Состав</h2>
          <table className={s.items}>
            <thead>
              <tr>
                <th>Позиция</th>
                <th className={s.num}>Цена</th>
                <th className={s.num}>Кол-во</th>
                <th className={s.num}>Сумма</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((it) => (
                <tr key={it.sku}>
                  <td>
                    {it.title}
                    <div className={s.muted}>{it.sku}</div>
                  </td>
                  <td className={`${s.num} tabular`}>{formatKopecks(it.unitPriceKopecks)}</td>
                  <td className={`${s.num} tabular`}>{it.quantity}</td>
                  <td className={`${s.num} tabular`}>{formatKopecks(it.lineTotalKopecks)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>Итого</td>
                <td className={`${s.num} tabular`} data-testid="order-total">
                  {formatKopecks(order.totalKopecks)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className={cls.card}>
          <h2 className={s.h2}>Клиент</h2>
          <dl className={s.dl}>
            <dt>Имя</dt>
            <dd>{order.customer.name}</dd>
            <dt>Телефон</dt>
            <dd>
              <a href={`tel:+${order.customer.phone}`}>{formatPhone(order.customer.phone)}</a>
            </dd>
            <dt>Город</dt>
            <dd>{order.customer.city ?? '—'}</dd>
          </dl>
        </div>
      </div>
    </section>
  )
}
