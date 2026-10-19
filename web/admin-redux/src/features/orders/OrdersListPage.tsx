import { Link } from 'react-router'
import { useListOrdersQuery } from '../../api/ordersApi'
import { ORDER_STATUSES } from '../../api/types'
import { useAppDispatch, useAppSelector } from '../../app/hooks'
import { Empty, ErrorBanner, Loading, StatusBadge } from '../../components/ui'
import cls from '../../components/ui.module.css'
import { formatDateTime } from '../../lib/date'
import { formatKopecks } from '../../lib/money'
import { formatPhone } from '../../lib/phone'
import {
  PAGE_SIZES,
  pageChanged,
  pageSizeChanged,
  selectOrdersFilter,
  selectOrdersQueryArgs,
  statusFilterChanged,
  totalPages,
  type StatusFilter,
} from '../ui/uiSlice'
import s from './OrdersListPage.module.css'
import { STATUS_LABEL } from './statusLabels'

const TABS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  ...ORDER_STATUSES.map((st) => ({ value: st, label: STATUS_LABEL[st] })),
]

export function OrdersListPage() {
  const dispatch = useAppDispatch()
  const filter = useAppSelector(selectOrdersFilter)
  const args = useAppSelector(selectOrdersQueryArgs)
  const { data, error, isLoading, isFetching, refetch } = useListOrdersQuery(args)
  const pages = data ? totalPages(data.total, data.limit) : 1

  return (
    <section className={s.page}>
      <div className={s.head}>
        <h1>Заказы</h1>
        {data && <span className={s.count}>{data.total}</span>}
        <Link to="/orders/new" className={`${cls.button} ${cls.primary}`}>
          Новый заказ
        </Link>
      </div>

      <div role="tablist" aria-label="Статус" className={s.tabs}>
        {TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={filter.status === t.value}
            className={s.tab}
            onClick={() => dispatch(statusFilterChanged(t.value))}
          >
            {t.label}
          </button>
        ))}
      </div>

      <ErrorBanner error={error} onRetry={() => void refetch()} />

      {isLoading ? (
        <Loading label="Загружаем заказы…" />
      ) : data && data.items.length === 0 ? (
        <Empty>{filter.status === 'all' ? 'Заказов пока нет' : `Нет заказов со статусом «${STATUS_LABEL[filter.status]}»`}</Empty>
      ) : data ? (
        <div className={`${cls.card} ${s.tableWrap}`} aria-busy={isFetching}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>№</th>
                <th>Дата</th>
                <th>Клиент</th>
                <th>Шт.</th>
                <th className={s.num}>Сумма</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody className={isFetching ? s.stale : undefined}>
              {data.items.map((o) => (
                <tr key={o.id}>
                  <td>
                    <Link to={`/orders/${o.id}`}>{o.id}</Link>
                  </td>
                  <td className="tabular">{formatDateTime(o.createdAt)}</td>
                  <td>
                    {o.customer.name}
                    <div className={s.sub}>
                      {formatPhone(o.customer.phone)}
                      {o.customer.city ? ` · ${o.customer.city}` : ''}
                    </div>
                  </td>
                  <td className="tabular">{o.items.reduce((n, i) => n + i.quantity, 0)}</td>
                  <td className={`${s.num} tabular`}>{formatKopecks(o.totalKopecks)}</td>
                  <td>
                    <StatusBadge status={o.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {data && data.total > 0 && (
        <nav className={s.pager} aria-label="Страницы">
          <button
            type="button"
            className={cls.button}
            disabled={filter.page <= 1}
            onClick={() => dispatch(pageChanged(filter.page - 1))}
          >
            ← Назад
          </button>
          <span className="tabular">
            Страница {filter.page} из {pages}
          </span>
          <button
            type="button"
            className={cls.button}
            disabled={filter.page >= pages}
            onClick={() => dispatch(pageChanged(filter.page + 1))}
          >
            Вперёд →
          </button>
          <label className={s.size}>
            По
            <select value={filter.limit} onChange={(e) => dispatch(pageSizeChanged(Number(e.target.value)))}>
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </nav>
      )}
    </section>
  )
}
