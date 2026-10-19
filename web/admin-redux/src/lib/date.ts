export function formatDateTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'short', timeStyle: 'short', timeZone }).format(new Date(iso))
}
