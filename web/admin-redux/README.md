# web/admin-redux — админка заказов на Redux Toolkit

Админка заказов магазина автомагнитол поверх [`services/orders-api-nest`](../../services/orders-api-nest):
список с фильтром и пагинацией, карточка заказа со сменой статуса, оформление заказа из каталога.

Стек: React 19, Vite 8, TypeScript 6 (strict, `noUncheckedIndexedAccess`), Redux Toolkit 2 + RTK Query,
React Router 7, CSS Modules. Тесты — Vitest 5, React Testing Library, MSW 3. ESLint 10 с `strictTypeChecked`.

React Router взят 7.x: 8.x требует Node ≥ 22.22, а проект проверялся на 22.15.
TypeScript 6.0, а не 7: typescript-eslint пока поддерживает `<6.1`.

## Зачем здесь Redux Toolkit и RTK Query

Данные приходят с сервера и меняются из нескольких мест (список, карточка, оформление), поэтому
серверное состояние живёт в **RTK Query**, а в обычных слайсах — только то, что принадлежит клиенту.

- **Кэш и теги.** `listOrders` даёт теги `Order:<id>` и `Order:LIST`, `getOrder` — `Order:<id>`.
  Создание заказа и смена статуса инвалидируют `LIST`, поэтому вкладки «Новый», «Подтверждён»
  перечитываются сами, а карточка не перезапрашивается: её кэш заменяется ответом PATCH (`upsertQueryData`).
- **Оптимистичное обновление** (`changeOrderStatus.onQueryStarted`). Статус меняется сразу в карточке
  и во всех закэшированных страницах списка (`selectInvalidatedBy` находит их по тегу заказа),
  кнопки переходов на время запроса скрыты. Ответ 409 `INVALID_TRANSITION` (заказ уже поменял
  другой администратор) — патчи откатываются, `formatApiError` пишет, в каком статусе заказ
  и куда его можно перевести, а тег `Order:<id>` инвалидируется, чтобы карточка перечиталась.
- **Кнопки по `allowedTransitions`.** Правила переходов знает только сервер, клиент их не дублирует.
- **`fixedCacheKey`** у мутации создания: отправку запускает thunk, а состояние запроса (загрузка,
  ошибка) читает форма через тот же ключ.
- **401 → разлогин.** Обёртка над `fetchBaseQuery` на 401 диспатчит `loggedOut('unauthorized')`;
  listener-middleware стирает токен из `sessionStorage` и сбрасывает весь кэш API, чтобы данные
  клиентов не остались в памяти.

Ключ идемпотентности (`Idempotency-Key`) хранится в слайсе черновика: создаётся при первой отправке,
повтор той же формы (после 5xx, таймаута, двойного клика) уходит с тем же ключом, любое изменение
формы его сбрасывает. Сервер на повтор отдаёт тот же заказ с `Idempotency-Replayed: true`, админка
пишет «второй не появился».

## Структура store

```
RootState
├── auth        { token, logoutReason }          — токен админки; дублируется в sessionStorage через listener
├── ui          { ordersFilter: { status, page, limit } } — вкладка и страница списка (смена статуса → страница 1)
├── orderDraft  { carId, lines[], customer, idempotencyKey } — черновик нового заказа, переживает уход со страницы
└── api         RTK Query: listOrders, getOrder, changeOrderStatus, createOrder,
                listCars, listKits, searchParts (каталог держится в кэше 10 минут)
```

Селекторы: `selectOrdersQueryArgs` (мемоизирован — тот же объект аргументов, пока фильтр не менялся),
`selectDraftTotalKopecks`, `selectCreateOrderBody` (без цен — их считает сервер; пустой город не отправляется).

```
src/
├── api/            baseApi (fetchBaseQuery + Bearer + 401), ordersApi, catalogApi, types (контракт API)
├── app/            store (combineSlices, listener), hooks, routes, Layout (защита маршрутов)
├── features/
│   ├── auth/       authSlice, tokenStorage, LoginPage
│   ├── ui/         uiSlice (фильтр списка)
│   ├── orders/     OrdersListPage, OrderDetailsPage, подписи статусов
│   └── new-order/  orderDraftSlice, submitOrder (thunk), NewOrderPage
├── components/     StatusBadge, ErrorBanner, Loading, Empty, FieldError
├── lib/            formatApiError, formatKopecks, даты, телефоны, config
└── test/           MSW-сервер, фикстуры, renderApp (store + memory router)
```

`formatApiError` — один путь для всех ошибок: формат API `{statusCode, code, message, details}`,
сетевые ошибки RTK Query (`FETCH_ERROR`, `TIMEOUT_ERROR`, `PARSING_ERROR`) и `SerializedError`.
Для `VALIDATION_FAILED` возвращает ошибки по полям (`customer.phone`, `items.1.quantity`),
форма показывает их под полем и у строки заказа.

Суммы везде в целых копейках; `formatKopecks` переводит в рубли целочисленно, без float.

## Запуск вместе с бэкендом

```sh
# 1. API (подробности — services/orders-api-nest/README.md)
cd services/orders-api-nest
docker compose up -d postgres
npm ci && npm run db:migrate && npm run db:seed
npm run start                      # http://localhost:3100, CORS открыт для http://localhost:5173

# 2. Админка
cd web/admin-redux
npm ci
cp .env.example .env.local         # только если API не на localhost:3100
npm run dev                        # http://localhost:5173
```

На экране входа ввести значение `ADMIN_API_TOKEN` из `services/orders-api-nest/.env`.
Токен в сборку не попадает и хранится только в `sessionStorage` вкладки. Это токен одной админки,
как и на сервере; для настоящего магазина нужен вход сотрудников с ролями.

Порт dev-сервера зафиксирован (5173, `strictPort`), потому что именно он разрешён в CORS API.

## Команды

```sh
npm test            # vitest run
npm run lint        # eslint
npm run typecheck   # tsc -b
npm run build       # tsc -b && vite build
```

## Тесты

**44 теста, 8 файлов.** Сеть в компонентных тестах — MSW, неописанный запрос завершается сетевой ошибкой (`onUnhandledFrame: 'error'`).

- `uiSlice` — редьюсеры (сброс страницы при смене статуса, границы), `selectOrdersQueryArgs` и его мемоизация.
- `authSlice` — вход/выход, селекторы; listener пишет токен в `sessionStorage` и при выходе стирает его вместе с кэшем API.
- `orderDraftSlice` — склейка одинаковых артикулов, итог в копейках, тело запроса; ключ идемпотентности
  стабилен при повторах и сбрасывается при каждом виде правки.
- `formatApiError`, `formatKopecks` — коды API, ошибки по полям, сетевые ошибки; копейки, большие суммы, отрицательные.
- `OrdersListPage` — заголовок `Authorization`, суммы и статусы, вкладки и пагинация через ui-slice,
  пустое состояние, ошибка с повтором, 401 → экран входа и пустой `sessionStorage`.
- `OrderDetailsPage` — состав, клиент, кнопки по `allowedTransitions`, конечный статус; оптимистичная
  смена статуса до ответа сервера; **409 — откат и в карточке, и в закэшированном списке**, понятное
  сообщение, перезапрос заказа.
- `NewOrderPage` — машина → комплект + поиск позиции → клиент → заказ; **повтор после 500 с тем же
  ключом, правка формы — новый ключ**; `Idempotency-Replayed`; ошибки 400 под полями; 422 со списком артикулов.

Прогон 19.10.2026 (Node 22.15):

```
npm test            Test Files  8 passed (8)   Tests  44 passed (44)
npm run lint        0 problems
npm run typecheck   без ошибок
npm run build       dist/assets/index-*.js 420 kB (gzip 135 kB), css 6.6 kB
```

Ручная проверка с живым API (Playwright, headless Chromium): без токена — редирект на вход; неверный
токен — разлогин с сообщением; список (422 заказа, 22 страницы по 20), вкладка «Доставлен»; форма:
телефон «123» → ошибка под полем, исправленный — заказ создан; переход «Новый → Подтверждён», появились
«Отгрузить» и «Отменить заказ»; выход очищает `sessionStorage`; ошибок в консоли нет.
