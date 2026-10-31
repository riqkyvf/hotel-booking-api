# Документация и эксплуатация

Основная инструкция: [README проекта](../README.md). Запуск из корня проекта: `docker compose up --build -d`.

Нормативные документы:

- [requirements.md](requirements.md) — функции, границы, идемпотентность, истечение, деактивация, платежи и конкурентные операции.
- [api-specification.md](api-specification.md) — 29 операций, параметры, авторизация, примеры, HTTP-коды и формат ошибок.
- [business-rules.md](business-rules.md) — стоимость, доступность и граф состояний.
- [database-schema.md](database-schema.md) — поля, типы, связи и ограничения.

## Адреса

Swagger: [localhost:8000/docs](http://localhost:8000/docs). OpenAPI: [localhost:8000/openapi.json](http://localhost:8000/openapi.json). Readiness: [localhost:8000/api/v1/health/ready](http://localhost:8000/api/v1/health/ready).

## Локальная БД / DBeaver

Драйвер PostgreSQL; host `localhost`, port `5433`, database `hotel`, user `hotel`, password `hotel_dev_password`, SSL disabled. При изменении `.env` используйте свои значения. JDBC URL: `jdbc:postgresql://localhost:5433/hotel`. Схема `public`. Для времён UTC выполните `SET TIME ZONE 'UTC'` в нужной SQL-сессии.

## Seed и сброс

Учётные записи: admin@example.com, admin2@example.com, alice@example.com, bob@example.com, disabled@example.com. Общий локальный пароль `HotelDemo123!`; последняя учётная запись неактивна. При первом старте seed выполняется автоматически, повторный запуск не изменяет данные.

Сброс без публичного HTTP-эндпоинта; команды выполняются из корня проекта и удаляют все данные приложения:

```powershell
docker compose stop api worker
docker compose run --rm --no-deps api python -m app.scripts.reset_db --confirm-reset
docker compose up -d
```

## Диагностика

`docker compose ps -a` показывает `db/api/worker` healthy и `init` exited (0). При проблемах используйте `docker compose logs --tail 100 init api worker db`. Проверка миграции: `docker compose exec api alembic current`, сверка моделей: `docker compose exec api alembic check`.

Worker повторяет проход через 5 секунд; healthcheck считает его готовым, если успешный проход был менее 60 секунд назад. Ошибки пишутся в stdout/stderr контейнеров. API возвращает request_id для сопоставления ошибок с журналом; секреты не включаются в ответы об ошибках.

Неоплаченные seed-брони меняют состояние со временем — это нормальное поведение. Точность проверки срока не зависит от частоты worker: API сверяет `clock_timestamp()` после получения блокировок.
