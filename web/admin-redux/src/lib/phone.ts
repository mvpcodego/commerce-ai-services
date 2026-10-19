/** «79001234567» → «+7 900 123-45-67»; всё остальное — как есть. */
export function formatPhone(phone: string): string {
  const m = /^7(\d{3})(\d{3})(\d{2})(\d{2})$/.exec(phone)
  return m ? `+7 ${m[1]} ${m[2]}-${m[3]}-${m[4]}` : phone
}
