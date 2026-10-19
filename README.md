# commerce-ai-services

Бэкенд-сервисы интернет-магазина автомагнитол: ИИ-продавец, агент закупок, фоновые задачи,
события, аналитика. Вынесены из закрытого проекта магазина (витрина и дашборд на Next.js
остались там); данные — синтетический каталог `seed/demo-data.json`: 40 автомобилей,
246 позиций, 286 комплектов, 420 заказов.

| Сервис | Что внутри | Стек |
|---|---|---|
| [`services/seller`](services/seller) | ИИ-продавец графом состояний: правила → классификатор → агент ⇄ инструменты, подтверждение заказа человеком, чекпоинты, трейсы, шлюз моделей | LangGraph, OpenTelemetry, LiteLLM |
| [`services/procurement-agent`](services/procurement-agent) | Агент закупок: свой MCP-сервер, хук-предохранитель, разрешения на каждый вызов | Claude Agent SDK |
| [`services/ops`](services/ops) | Очередь задач на Postgres (SKIP LOCKED), Celery на RabbitMQ, события заказов из Kafka, аналитика в ClickHouse, REST и gRPC | FastAPI, SQLAlchemy 2.0, Alembic, aiokafka, clickhouse-connect, grpcio |
| [`services/knowledge-rag`](services/knowledge-rag) | RAG по базе знаний магазина: гибридный поиск (вектор + полнотекст, RRF, переранжирование), ответ строго по источнику с проверкой цитат, оценка качества поиска (Recall@5, MRR, nDCG) | pgvector, fastembed (multilingual-e5), FastAPI |
| [`services/orders-api-nest`](services/orders-api-nest) | API заказов: идемпотентное создание, переходы статусов, outbox → Kafka, Swagger, доступ к данным клиентов по токену | NestJS, TypeORM, PostgreSQL, kafkajs, Jest |
| [`web/admin-redux`](web/admin-redux) | Админка заказов: список с фильтрами, карточка с оптимистичной сменой статуса и откатом, форма заказа с ключом идемпотентности | React, Redux Toolkit, RTK Query, Vitest, MSW |
| [`monitoring`](monitoring) | Метрики сервисов и сервера, дашборд и оповещения в Telegram | Prometheus, Grafana |
| [`web/order-events.ts`](web/order-events.ts) | Продюсер событий `order.created` из витрины | kafkajs |
| [`lib/analytics/procurement.ts`](lib/analytics/procurement.ts) | Расчёт закупок из дашборда — эталон, с которым тесты сверяют Python-порт в ops | TypeScript |

## Что стоит посмотреть

- `services/seller/README.md` — граф продавца, остановка перед заказом через `interrupt`,
  вывод «LangGraph или прямой SDK» на одной задаче.
- `services/procurement-agent/README.md` — почему `allowed_tools` пуст и чем хук отличается от промпта.
- `services/ops/README.md` — две очереди и зачем обе; at-least-once с идемпотентностью для Kafka;
  замер ClickHouse против Postgres на 5 млн строк; gRPC-стрим вместо опроса.

## Тесты

```bash
cd services/seller && uv sync && uv run pytest              # 36, модель — сценарий, ключи не нужны
cd services/procurement-agent && uv sync && uv run pytest   # 10, модель не вызывается
cd services/ops && uv sync && uv run pytest                 # 38, нужен Postgres (см. tests/conftest.py) и Node 22
cd services/knowledge-rag && uv sync && uv run pytest      # 29, тесты с БД пропускаются без pgvector
cd services/orders-api-nest && npm ci && npm test          # 42 unit; e2e — npm run test:e2e (21, нужен Postgres)
cd web/admin-redux && npm ci && npm test                    # 44, API мокается через MSW
```

Сквозные тесты с Kafka и ClickHouse включаются, когда брокер и база доступны
(`docker-compose.kafka.yml`, `docker-compose.analytics.yml`), иначе пропускаются.

Автор — Павел Чертинов, [mvp-code.ru](https://mvp-code.ru), Telegram [@pavelCity](https://t.me/pavelCity).
