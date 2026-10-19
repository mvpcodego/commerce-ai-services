/** Intl в ru-RU ставит неразрывные пробелы — в проверках сравниваем с обычными. */
export const plain = (s: string | null | undefined): string => (s ?? '').replace(/[\u00a0\u202f]/g, ' ')
