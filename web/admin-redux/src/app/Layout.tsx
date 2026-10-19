import { Navigate, NavLink, Outlet, useLocation } from 'react-router'
import cls from '../components/ui.module.css'
import { loggedOut, selectIsAuthenticated } from '../features/auth/authSlice'
import { useAppDispatch, useAppSelector } from './hooks'
import s from './Layout.module.css'

/** Оболочка админки: без токена — на вход, с возвратом туда, куда шли. */
export function Layout() {
  const dispatch = useAppDispatch()
  const location = useLocation()
  const isAuthenticated = useAppSelector(selectIsAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />

  return (
    <div className={s.shell}>
      <header className={s.header}>
        <span className={s.brand}>Магнитолы · заказы</span>
        <nav className={s.nav}>
          <NavLink to="/orders" end className={({ isActive }) => (isActive ? s.active : undefined)}>
            Заказы
          </NavLink>
          <NavLink to="/orders/new" className={({ isActive }) => (isActive ? s.active : undefined)}>
            Новый заказ
          </NavLink>
        </nav>
        <button
          type="button"
          className={cls.button}
          onClick={() => {
            dispatch(loggedOut('manual'))
          }}
        >
          Выйти
        </button>
      </header>
      <main className={s.main}>
        <Outlet />
      </main>
    </div>
  )
}
