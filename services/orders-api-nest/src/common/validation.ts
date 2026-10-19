import { BadRequestException, ValidationError, ValidationPipe } from "@nestjs/common"

type FieldError = { field: string; errors: string[] }

export function flattenErrors(errors: ValidationError[], prefix = ""): FieldError[] {
  return errors.flatMap((e) => {
    const field = prefix ? `${prefix}.${e.property}` : e.property
    const own = e.constraints ? [{ field, errors: Object.values(e.constraints) }] : []
    return [...own, ...flattenErrors(e.children ?? [], field)]
  })
}

/** Глобальная валидация DTO: лишние поля — ошибка, типы приводятся по декораторам. */
export function createValidationPipe(): ValidationPipe {
  return new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    exceptionFactory: (errors) =>
      new BadRequestException({ code: "VALIDATION_FAILED", message: "Запрос не прошёл проверку", details: flattenErrors(errors) }),
  })
}
