/** Ошибка предметной области: код для клиента + HTTP-статус. Превращается в ответ в ApiExceptionFilter. */
export class DomainError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message)
  }
}
