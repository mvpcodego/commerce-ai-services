import { useState, type SubmitEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAppDispatch, useAppSelector } from '../../app/hooks'
import cls from '../../components/ui.module.css'
import { loggedIn, selectIsAuthenticated, selectLogoutReason } from './authSlice'
import s from './LoginPage.module.css'

export function LoginPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const location = useLocation()
  const isAuthenticated = useAppSelector(selectIsAuthenticated)
  const reason = useAppSelector(selectLogoutReason)
  const [token, setToken] = useState('')

  const from = (location.state as { from?: string } | null)?.from ?? '/orders'
  if (isAuthenticated) return <Navigate to={from} replace />

  function submit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!token.trim()) return
    dispatch(loggedIn(token))
    void navigate(from, { replace: true })
  }

  return (
    <main className={s.wrap}>
      <form className={`${cls.card} ${s.form}`} onSubmit={submit}>
        <h1>Админка заказов</h1>
        <p className={s.hint}>
          Токен — значение <code>ADMIN_API_TOKEN</code> из настроек API. Хранится только в этой вкладке.
        </p>
        {reason === 'unauthorized' && (
          <div role="alert" className={cls.error}>
            Сервер не принял токен. Проверьте его и войдите снова.
          </div>
        )}
        <label className={s.label}>
          Токен админки
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => {
              setToken(e.target.value)
            }}
            autoFocus
          />
        </label>
        <button type="submit" className={`${cls.button} ${cls.primary}`} disabled={!token.trim()}>
          Войти
        </button>
      </form>
    </main>
  )
}
