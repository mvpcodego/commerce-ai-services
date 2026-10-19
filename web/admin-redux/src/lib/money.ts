const rubles = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })

/** 3550000 → «35 500 ₽», 12345 → «123,45 ₽». Считаем в целых копейках, без float. */
export function formatKopecks(kopecks: number): string {
  if (!Number.isSafeInteger(kopecks)) throw new TypeError(`Сумма должна быть целым числом копеек: ${kopecks}`)
  const sign = kopecks < 0 ? '−' : ''
  const abs = Math.abs(kopecks)
  const rub = Math.trunc(abs / 100)
  const kop = abs % 100
  const fraction = kop === 0 ? '' : `,${String(kop).padStart(2, '0')}`
  return `${sign}${rubles.format(rub)}${fraction}\u00a0₽`
}
