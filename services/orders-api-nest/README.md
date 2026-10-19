# services/orders-api-nest — API заказов на NestJS

API заказов магазина автомагнитол: каталог (только чтение), оформление заказа с ключом
идемпотентности, список и карточка для админки, смена статуса по разрешённым переходам,
событие `order.created` в Kafka через outbox. Данные — синтетический `seed/demo-data.json`
(40 автомобилей, 246 позиций, 286 комплектов, 420 заказов).

Стек: Node 22, NestJS 12 (ESM), TypeScript 6, PostgreSQL 16, TypeORM 1.x, kafkajs,
class-validator, Swagger (`@nestjs/swagger`), Jest 30 + supertest, ESLint (typescript-eslint).

**Почему TypeORM, а не Prisma:** нужны явная транзакция «ключ + заказ + outbox» через `EntityManager`
и `FOR UPDATE SKIP LOCKED` для релея — в TypeORM это обычный код и SQL, миграции — TS-классы без
отдельного движка.

## Эндпоинты

Порт `3100`, OpenAPI — `http://localhost:3100/docs` (JSON — `/docs-json`).
Все суммы — **целые копейки** (`priceKopecks`, `totalKopecks`). Цены в заказ клиент не передаёт:
они берутся из каталога.

| Метод и путь | Доступ | Что делает |
|---|---|---|
| `GET /health` | открыт | база доступна, сколько событий ждут публикации |
| `GET /catalog/parts?type=&q=&page=&limit=` | открыт | позиции без архивных; фильтр по типу, поиск по названию и артикулу |
| `GET /catalog/parts/:sku` | открыт | позиция |
| `GET /catalog/cars` | открыт | автомобили |
| `GET /catalog/kits?carId=&page=&limit=` | открыт | комплекты |
| `GET /catalog/kits/:sku` | открыт | комплект (`kit-12`) с автомобилем и составом |
| `POST /orders` + `Idempotency-Key` | открыт (витрина) | оформить заказ, 201 |
| `GET /orders?status=&page=&limit=` | токен админки | список, новые сверху |
| `GET /orders/:id` | токен админки | карточка заказа |
| `PATCH /orders/:id/status` | токен админки | сменить статус, `{ "status": "confirmed" }` |

**Кто что может.** Каталог и оформление — публичные (это витрина). Список и карточка заказа отдают
имя и телефон покупателя, смена статуса меняет данные — эти маршруты закрыты `AdminTokenGuard`:
`Authorization: Bearer <ADMIN_API_TOKEN>`, сравнение по хэшу фиксированной длины. Без
`ADMIN_API_TOKEN` (или короче 16 символов) приложение не стартует. Это токен одной админки,
а не пользователи с ролями — для демо-сервиса достаточно, для настоящего магазина нужен вход сотрудников.

Заказ в ответах:

```json
{
  "id": 421, "status": "new", "allowedTransitions": ["confirmed", "cancelled"],
  "customer": { "name": "Роман Ершов", "phone": "79000000000", "city": "Казань" },
  "items": [{ "sku": "kit-47", "title": "Hyundai Solaris + Nordvox N2 9\"", "unitPriceKopecks": 3550000, "quantity": 1, "lineTotalKopecks": 3550000 }],
  "totalKopecks": 3550000, "createdAt": "2026-10-19T10:45:59.210Z", "updatedAt": "2026-10-19T10:45:59.210Z"
}
```

Список: `{ items: Order[], total, page, limit }`, `limit` 1–100 (по умолчанию 20).

Тело `POST /orders`: `{ customer: { name 2–100, phone, city? }, items: [{ sku, quantity 1–99 }] }`,
1–50 строк, артикул не повторяется. Телефон в любом виде (`+7 (900) …`, `8 900 …`) хранится как `7XXXXXXXXXX`.
Лишние поля (например, `price`) — ошибка валидации.

Статусы: `new → confirmed | cancelled`, `confirmed → shipped | cancelled`, `shipped → delivered`;
`delivered` и `cancelled` конечные. Куда можно перейти сейчас — поле `allowedTransitions`,
админке не нужно дублировать правила.

Ошибки — один формат для всех маршрутов (`ApiExceptionFilter`):

```json
{ "statusCode": 409, "code": "INVALID_TRANSITION", "message": "Нельзя перевести заказ из «new» в «delivered»",
  "details": { "from": "new", "to": "delivered", "allowed": ["confirmed", "cancelled"] },
  "path": "/orders/421/status", "timestamp": "2026-10-19T10:45:59.314Z" }
```

| Код | Статус | Когда |
|---|---|---|
| `VALIDATION_FAILED` | 400 | тело или query не прошли проверку; `details: [{ field, errors[] }]`, поля вложенные: `customer.phone`, `items.0.quantity` |
| `IDEMPOTENCY_KEY_REQUIRED` / `_INVALID` | 400 | нет заголовка / не 8–255 символов `A-Z a-z 0-9 . _ : -` |
| `UNAUTHORIZED` | 401 | нет или неверный токен админки |
| `ORDER_NOT_FOUND`, `PART_NOT_FOUND`, `KIT_NOT_FOUND` | 404 | |
| `IDEMPOTENCY_KEY_REUSED` | 409 | ключ уже был с другим телом |
| `INVALID_TRANSITION` | 409 | переход не разрешён (в т.ч. гонка двух админов) |
| `UNKNOWN_SKU` | 422 | артикула нет или он в архиве; `details.skus` — все такие |
| `DB_UNAVAILABLE` | 503 | `/health`, база не отвечает |
| `INTERNAL` | 500 | без подробностей наружу, стек — в лог |

CORS открыт для `CORS_ORIGINS` (по умолчанию `http://localhost:5173`), методы GET/POST/PATCH,
заголовки `Authorization`, `Idempotency-Key`; браузеру виден ответный `Idempotency-Replayed`.

## Идемпотентность создания заказа

Клиент генерирует ключ (UUID) на попытку оформления и шлёт его при каждом повторе.

1. В одной транзакции: `INSERT INTO idempotency_keys (key, request_hash) … ON CONFLICT DO NOTHING`.
   `request_hash` — SHA-256 канонического JSON тела после валидации (ключи по алфавиту, так что
   порядок полей и формат телефона не делают «другой запрос»).
2. Ключ новый — цены из каталога, заказ, строки, ответ сохраняется в строке ключа, событие — в outbox. Коммит.
3. Ключ уже есть: хэш тот же — отдаётся **сохранённый** ответ (тот же, даже если статус с тех пор
   сменился), 201 и `Idempotency-Replayed: true`; хэш другой — 409 `IDEMPOTENCY_KEY_REUSED`.
4. Параллельные запросы с одним ключом: второй `INSERT … ON CONFLICT` ждёт, пока первая транзакция
   закоммитится, и получает её ответ. Тест: 10 одновременных запросов → один заказ.
5. Ошибка (422, сбой базы) откатывает и ключ — исправленный запрос можно отправить с тем же ключом.

Срок жизни ключей не ограничен: чистки старых ключей нет (для боевого — удалять старше суток задачей по расписанию).

## События: outbox, а не «отправить после коммита»

Отправка в Kafka после коммита теряет событие, если процесс упал между коммитом и отправкой,
а отправка до коммита публикует заказ, которого может не оказаться. Поэтому:

- `order.created` пишется в таблицу `outbox` **в той же транзакции**, что и заказ: есть заказ — есть событие.
- `OutboxRelay` раз в `OUTBOX_POLL_MS` берёт до 100 неопубликованных строк
  `FOR UPDATE SKIP LOCKED` (несколько экземпляров API не отправят одно событие одновременно),
  отправляет пачкой идемпотентным продюсером kafkajs (`acks: -1`) и ставит `published_at`.
- Брокер недоступен — `attempts + 1`, `last_error`, следующая попытка через 2, 4, 8 … секунд (не больше 5 минут).
- Доставка at-least-once: упали между ответом брокера и коммитом — событие уйдёт ещё раз с тем же
  `event_id`, дубли отсекает потребитель.
- Без `KAFKA_BROKERS` релей не запускается, события копятся в outbox (видно в `/health`).

Событие совместимо с потребителем `services/ops` (`ops/events.py`): топик `orders`, ключ — id заказа
(события одного заказа идут в одну партицию по порядку), заголовки `event-id`, `event-type`:

```json
{ "event_id": "f03bb7d4-…", "type": "order.created", "occurred_at": "2026-10-19T10:45:59.210Z",
  "order_id": 421, "items": [{ "sku": "kit-47", "quantity": 1 }], "total_kopecks": 3550000 }
```

Имени и телефона в событии нет. Сумма — в копейках, поэтому поле называется `total_kopecks`,
а не `total`, как в `web/order-events.ts`: единицы видны из имени.

Транзакция релея держится, пока брокер отвечает на пачку: на большом потоке пачку лучше уменьшить
или помечать строки «в работе» отдельным шагом.

## База

Миграция `src/db/migrations/1760860800000-init.ts`: `cars`, `parts`, `kits` (каталог), `orders`,
`order_items`, `idempotency_keys`, `outbox` (частичный индекс по неопубликованным). CHECK на статусы
и неотрицательные суммы. Итоги — `bigint`, цены строк — `int`.

Сид (`src/db/seed.ts`): каталог — upsert по id (повторный запуск обновляет цены и остатки),
цены из рублей в копейки; 420 исторических заказов — только в пустую таблицу, без событий в outbox,
после них последовательность id продолжается.

Остатки при оформлении не проверяются и не резервируются: в демо-данных у части позиций `stock: 0`,
а магазин работает и под заказ.

## Запуск

```sh
cp .env.example .env                  # и задать ADMIN_API_TOKEN: openssl rand -hex 32
docker compose up -d postgres         # Postgres 16 на 127.0.0.1:5436
docker compose up -d kafka            # по желанию: брокер KRaft на 127.0.0.1:9094
npm ci
npm run db:migrate                    # сборка + миграции
npm run db:seed                       # каталог + исторические заказы (--catalog-only — только каталог)
npm run start                         # http://localhost:3100, /docs
```

Проверка вручную:

```sh
curl -X POST localhost:3100/orders -H 'content-type: application/json' -H "Idempotency-Key: $(uuidgen)" \
  -d '{"customer":{"name":"Тест Тестов","phone":"+7 900 000-00-01"},"items":[{"sku":"kit-47","quantity":1}]}'
curl localhost:3100/orders?status=new -H "Authorization: Bearer $ADMIN_API_TOKEN"
docker exec orders-nest-kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9094 --topic orders --from-beginning --property print.key=true
```

## Тесты

```sh
npm test            # unit, база не нужна
npm run test:e2e    # e2e против Postgres (база orders_test создаётся сама); без БД — пропускаются
npm run lint && npm run typecheck
```

NestJS 12 поставляется только как ESM, поэтому Jest запускается с `--experimental-vm-modules`,
ts-jest — в режиме `useESM` (шаблон `nest new` теперь предлагает Vitest; здесь оставлен Jest).

**Unit — 42 теста, 7 файлов:** переходы статусов (все разрешённые и запрещённые); хэш тела
(порядок ключей, undefined-поля, порядок строк) и проверка ключа; цена заказа в копейках и 422
со списком артикулов; валидация DTO (нормализация телефона, запрет `price`, повтор артикула,
приведение query); `OrdersService` на менеджере в памяти (новый ключ, повтор, 409, 422 без заказа,
переходы, 404); формат ошибок фильтра (500 без подробностей); токен админки.

**e2e — 21 тест, 2 файла, реальный Postgres:** health, OpenAPI, CORS (чужой origin не получает
разрешения); каталог (фильтр, поиск, состав комплекта, 404 и 400 в общем формате); создание
и повтор, повтор после смены статуса отдаёт исходный ответ, 409 на другое тело, **10 параллельных
запросов с одним ключом → один заказ**, 400 без ключа, 422 не сжигает ключ; outbox: одно событие
на заказ без ПДн, повтор не добавляет событие, сбой брокера → попытка, ошибка, пауза, затем отправка;
админка: 401 без токена, пагинация и фильтр, полный путь статусов и 409, **два одновременных
подтверждения → 200 и 409**; живой прогон Kafka: заказ → outbox → топик `orders` → потребитель
читает событие (пропускается, если брокер на 9094 не поднят).

Результат прогона 19.10.2026 (Node 22.15, Postgres 16, Kafka 3.9.1 в Docker):

```
npm test          Test Suites: 7 passed, 7 total   Tests: 42 passed, 42 total
npm run test:e2e  Test Suites: 2 passed, 2 total   Tests: 21 passed, 21 total
npm run lint      0 problems
```

## Настройки

| Переменная | По умолчанию | |
|---|---|---|
| `PORT` | `3100` | |
| `DATABASE_URL` | `postgres://orders:orders@localhost:5436/orders` | |
| `ADMIN_API_TOKEN` | — | обязателен, от 16 символов |
| `CORS_ORIGINS` | `http://localhost:5173` | через запятую |
| `KAFKA_BROKERS` | пусто | пусто — события остаются в outbox |
| `OUTBOX_POLL_MS` | `1000` | `0` — релей выключен |
| `TEST_DATABASE_URL` | `…:5436/orders_test` | для e2e |
| `KAFKA_TEST_BROKERS` | `localhost:9094` | для живого прогона Kafka |
