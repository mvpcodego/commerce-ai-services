import { render } from '@testing-library/react'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { routes } from '../app/routes'
import { makeStore, type RootState } from '../app/store'

export const TEST_TOKEN = 'test-token-0123456789'

export function renderApp(path: string, preloaded: Partial<RootState> = { auth: { token: TEST_TOKEN, logoutReason: null } }) {
  const store = makeStore(preloaded)
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  const utils = render(
    <Provider store={store}>
      <RouterProvider router={router} />
    </Provider>,
  )
  return { ...utils, store, router }
}
