import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Provider } from 'react-redux'
import { App } from './app/App'
import { initialStateFromStorage, makeStore } from './app/store'
import './index.css'

const store = makeStore(initialStateFromStorage())

const root = document.getElementById('root')
if (!root) throw new Error('#root не найден')

createRoot(root).render(
  <StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </StrictMode>,
)
