// Токен живёт только в sessionStorage вкладки: закрыли вкладку — нужно войти снова.
const KEY = 'admin-redux.token'

export function readToken(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function writeToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(KEY, token)
    else sessionStorage.removeItem(KEY)
  } catch {
    // приватный режим или запрет хранилища — работаем без сохранения
  }
}
