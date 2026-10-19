import { useEffect, useId, useState, type SubmitEvent } from 'react'
import { useNavigate } from 'react-router'
import { useListCarsQuery, useListKitsQuery, useSearchPartsQuery } from '../../api/catalogApi'
import { useCreateOrderMutation } from '../../api/ordersApi'
import { useAppDispatch, useAppSelector } from '../../app/hooks'
import { Empty, ErrorBanner, FieldError } from '../../components/ui'
import cls from '../../components/ui.module.css'
import { formatApiError } from '../../lib/apiError'
import { formatKopecks } from '../../lib/money'
import s from './NewOrderPage.module.css'
import {
  carSelected,
  customerChanged,
  draftReset,
  lineAdded,
  lineRemoved,
  MAX_QUANTITY,
  quantityChanged,
  selectDraft,
  selectDraftTotalKopecks,
} from './orderDraftSlice'
import { CREATE_ORDER_KEY, submitOrder } from './submitOrder'

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(value)
    }, ms)
    return () => {
      clearTimeout(t)
    }
  }, [value, ms])
  return debounced
}

export function NewOrderPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const draft = useAppSelector(selectDraft)
  const total = useAppSelector(selectDraftTotalKopecks)
  const [, { isLoading: isSubmitting, error, reset }] = useCreateOrderMutation({ fixedCacheKey: CREATE_ORDER_KEY })
  const formatted = error ? formatApiError(error) : null
  const fieldErrors = formatted?.fieldErrors ?? {}

  // Ошибка прошлой отправки не должна встречать при следующем заходе на страницу.
  useEffect(() => reset, [reset])

  async function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (isSubmitting) return
    try {
      const { order, replayed } = await dispatch(submitOrder()).unwrap()
      dispatch(draftReset())
      reset()
      void navigate(`/orders/${order.id}`, { state: { created: replayed ? 'replayed' : 'new' } })
    } catch {
      // ошибка уже в состоянии мутации (fixedCacheKey) и показывается ниже
    }
  }

  return (
    <form className={s.page} onSubmit={(e) => void submit(e)} noValidate>
      <h1>Новый заказ</h1>

      <div className={s.grid}>
        <div className={s.column}>
          <CarAndKits carId={draft.carId} />
          <PartSearch />
        </div>

        <div className={s.column}>
          <section className={cls.card} aria-labelledby="lines-h">
            <h2 id="lines-h" className={s.h2}>
              Состав заказа
            </h2>
            {draft.lines.length === 0 ? (
              <Empty>Добавьте комплект или позицию из каталога</Empty>
            ) : (
              <ul className={s.lines}>
                {draft.lines.map((l, i) => (
                  <li key={l.sku} className={s.line}>
                    <div className={s.lineTitle}>
                      {l.title}
                      <div className={s.muted}>
                        {l.sku} · {formatKopecks(l.unitPriceKopecks)}
                      </div>
                      <FieldError messages={fieldErrors[`items.${i}.quantity`]} />
                    </div>
                    <input
                      type="number"
                      min={1}
                      max={MAX_QUANTITY}
                      className={s.qty}
                      aria-label={`Количество: ${l.title}`}
                      value={l.quantity}
                      onChange={(e) => dispatch(quantityChanged({ sku: l.sku, quantity: e.target.valueAsNumber }))}
                    />
                    <button
                      type="button"
                      className={cls.button}
                      aria-label={`Убрать ${l.title}`}
                      onClick={() => dispatch(lineRemoved(l.sku))}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <FieldError messages={fieldErrors.items} />
            <div className={s.total}>
              <span>Итого</span>
              <span className="tabular" data-testid="draft-total">
                {formatKopecks(total)}
              </span>
            </div>
            <p className={s.muted}>Окончательные цены считает сервер по каталогу.</p>
          </section>

          <section className={cls.card} aria-labelledby="customer-h">
            <h2 id="customer-h" className={s.h2}>
              Клиент
            </h2>
            <div className={s.fields}>
              <TextField
                label="Имя"
                value={draft.customer.name}
                errors={fieldErrors['customer.name']}
                onChange={(name) => dispatch(customerChanged({ name }))}
              />
              <TextField
                label="Телефон"
                type="tel"
                placeholder="+7 900 000-00-00"
                value={draft.customer.phone}
                errors={fieldErrors['customer.phone']}
                onChange={(phone) => dispatch(customerChanged({ phone }))}
              />
              <TextField
                label="Город"
                hint="необязательно"
                value={draft.customer.city}
                errors={fieldErrors['customer.city']}
                onChange={(city) => dispatch(customerChanged({ city }))}
              />
            </div>
          </section>

          {formatted && (
            <div role="alert" className={cls.error}>
              {formatted.message}
            </div>
          )}

          <div className={s.submitRow}>
            <button type="submit" className={`${cls.button} ${cls.primary}`} disabled={isSubmitting || draft.lines.length === 0}>
              {isSubmitting ? 'Отправляем…' : 'Оформить заказ'}
            </button>
            {draft.idempotencyKey && (
              <span className={s.muted} title="Повторная отправка этой же формы уйдёт с этим ключом">
                ключ попытки: <code data-testid="idempotency-key">{draft.idempotencyKey.slice(0, 8)}…</code>
              </span>
            )}
          </div>
        </div>
      </div>
    </form>
  )
}

function CarAndKits({ carId }: { carId: number | null }) {
  const dispatch = useAppDispatch()
  const cars = useListCarsQuery(undefined)
  const kits = useListKitsQuery(carId ?? 0, { skip: carId === null })

  return (
    <section className={cls.card} aria-labelledby="kits-h">
      <h2 id="kits-h" className={s.h2}>
        Комплект под автомобиль
      </h2>
      <ErrorBanner error={cars.error} onRetry={() => void cars.refetch()} />
      <label className={s.label}>
        Автомобиль
        <select
          value={carId ?? ''}
          disabled={!cars.data}
          onChange={(e) => dispatch(carSelected(e.target.value ? Number(e.target.value) : null))}
        >
          <option value="">{cars.isLoading ? 'Загрузка…' : 'Выберите автомобиль'}</option>
          {cars.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.make} {c.model}
              {c.generation ? ` ${c.generation}` : ''}
              {c.yearFrom ? ` (${c.yearFrom}–${c.yearTo ?? 'н. в.'})` : ''}
            </option>
          ))}
        </select>
      </label>
      {carId !== null && (
        <>
          <ErrorBanner error={kits.error} />
          {kits.isFetching && !kits.data ? (
            <p className={s.muted}>Загружаем комплекты…</p>
          ) : kits.data?.items.length === 0 ? (
            <p className={s.muted}>Для этого автомобиля комплектов нет — добавьте позиции поиском</p>
          ) : (
            <ul className={s.options}>
              {kits.data?.items.map((k) => (
                <li key={k.sku}>
                  <span>
                    {k.title}
                    {k.isDefault && <span className={s.muted}> · базовый</span>}
                  </span>
                  <span className="tabular">{formatKopecks(k.priceKopecks)}</span>
                  <button
                    type="button"
                    className={cls.button}
                    onClick={() => dispatch(lineAdded({ sku: k.sku, title: k.title, unitPriceKopecks: k.priceKopecks }))}
                  >
                    Добавить
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}

function PartSearch() {
  const dispatch = useAppDispatch()
  const [q, setQ] = useState('')
  const term = useDebounced(q.trim(), 300)
  const parts = useSearchPartsQuery(term, { skip: term.length < 2 })

  return (
    <section className={cls.card} aria-labelledby="parts-h">
      <h2 id="parts-h" className={s.h2}>
        Позиции из каталога
      </h2>
      <label className={s.label}>
        Поиск по названию или артикулу
        <input
          type="search"
          value={q}
          placeholder="например, рамка или камера"
          onChange={(e) => {
            setQ(e.target.value)
          }}
        />
      </label>
      <ErrorBanner error={parts.error} />
      {term.length >= 2 && parts.data?.items.length === 0 && <p className={s.muted}>Ничего не нашлось</p>}
      {term.length >= 2 && parts.data && parts.data.items.length > 0 && (
        <ul className={s.options}>
          {parts.data.items.map((p) => (
            <li key={p.sku}>
              <span>
                {p.title}
                <span className={s.muted}>
                  {' '}
                  · {p.sku}
                  {p.stock === 0 ? ' · под заказ' : ''}
                </span>
              </span>
              <span className="tabular">{formatKopecks(p.priceKopecks)}</span>
              <button
                type="button"
                className={cls.button}
                onClick={() => dispatch(lineAdded({ sku: p.sku, title: p.title, unitPriceKopecks: p.priceKopecks }))}
              >
                Добавить
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function TextField(props: {
  label: string
  value: string
  onChange: (value: string) => void
  errors: string[] | undefined
  type?: 'text' | 'tel'
  placeholder?: string
  hint?: string
}) {
  const id = useId()
  const invalid = !!props.errors?.length
  return (
    <div className={s.label}>
      <label htmlFor={id}>
        {props.label} {props.hint && <span className={s.muted}>{props.hint}</span>}
      </label>
      <input
        id={id}
        type={props.type ?? 'text'}
        placeholder={props.placeholder}
        value={props.value}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-error` : undefined}
        onChange={(e) => {
          props.onChange(e.target.value)
        }}
      />
      <FieldError id={`${id}-error`} messages={props.errors} />
    </div>
  )
}
