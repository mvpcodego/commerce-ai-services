import { Navigate, type RouteObject } from 'react-router'
import { LoginPage } from '../features/auth/LoginPage'
import { NewOrderPage } from '../features/new-order/NewOrderPage'
import { OrderDetailsPage } from '../features/orders/OrderDetailsPage'
import { OrdersListPage } from '../features/orders/OrdersListPage'
import { Layout } from './Layout'

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/orders" replace /> },
      { path: 'orders', element: <OrdersListPage /> },
      { path: 'orders/new', element: <NewOrderPage /> },
      { path: 'orders/:id', element: <OrderDetailsPage /> },
      { path: '*', element: <Navigate to="/orders" replace /> },
    ],
  },
]
