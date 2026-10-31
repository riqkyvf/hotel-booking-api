# Hotel Booking API

REST API для самостоятельной QA/AQA-практики: FastAPI, PostgreSQL, SQLAlchemy 2, Alembic, JWT. Frontend отсутствует. Все платежи тестовые.

## Запуск

Нужен запущенный Docker Desktop с Linux containers и Docker Compose. Откройте терминал в папке проекта:

```powershell
docker compose up --build -d
docker compose ps -a
```

Настройка `.env` не обязательна: Compose содержит локальные значения по умолчанию. Для своих настроек:

```powershell
Copy-Item .env.example .env
```

После старта доступны:

- [Swagger UI](http://localhost:8000/docs)
- [OpenAPI JSON](http://localhost:8000/openapi.json)
- [API readiness](http://localhost:8000/api/v1/health/ready)
- PostgreSQL: `localhost:5433`.

Внешний порт БД — 5433, чтобы не конфликтовать с локальным PostgreSQL на 5432. Внутри Docker БД использует стандартный порт 5432.

Контейнер `init` должен завершиться с кодом 0 — это нормально. Он применяет миграции и seed. API и worker стартуют после него. Сервисы `db`, `api`, `worker` имеют healthcheck; worker проверяется по времени последнего успешного прохода. Seed не заменяет данные при повторном запуске.

## Учётные записи

Общий локальный пароль по умолчанию: **`HotelDemo123!`**. Его можно изменить переменной `SEED_PASSWORD` до первого seed или сброса БД.

| Email | Роль | Активность |
|---|---|---|
| admin@example.com | admin | Да |
| admin2@example.com | admin | Да |
| alice@example.com | user | Да |
| bob@example.com | user | Да |
| disabled@example.com | user | Нет |

В Swagger выполните POST `/api/v1/auth/login`:

```json
{"email":"alice@example.com","password":"HotelDemo123!"}
```

Скопируйте `access_token` в кнопку **Authorize** без слова Bearer. Токен действует 60 минут. API также принимает обычный заголовок `Authorization: Bearer <token>`.

Seed содержит 5 отелей в разных городах, 25 физических номеров, 8 бронирований и 7 платежей. Даты вычисляются относительно UTC-дня seed. Один номер отключён для новых бронирований; есть данные отключённого пользователя. Все статусы представлены сразу после заполнения. Неоплаченные брони закономерно истекают со временем; для возврата начального состояния предусмотрен сброс.

## Документация

- [Требования и согласованные уточнения](docs/requirements.md)
- [API, параметры, примеры и ошибки](docs/api-specification.md)
- [Бизнес-правила и состояния](docs/business-rules.md)
- [Схема базы данных](docs/database-schema.md)
- [Эксплуатация и подключение к БД](docs/README.md)
- [Исходное архитектурное предложение](ARCHITECTURE_PROPOSAL.md)

Требования в docs уточняют исходное архитектурное предложение. API не содержит намеренных дефектов; пользовательский набор QA-тестов не включён.

## Остановка, логи, миграции

```powershell
docker compose logs --tail 100 api worker init
docker compose exec api alembic current
docker compose exec api alembic check
docker compose stop
docker compose up -d
```

Изменения в исходниках включаются в образ командой `docker compose up --build -d`.

## Сброс к начальным данным

Следующие команды **удаляют все данные приложения**, затем заново применяют миграцию и seed. Сначала обязательно остановить API и worker:

```powershell
docker compose stop api worker
docker compose run --rm --no-deps api python -m app.scripts.reset_db --confirm-reset
docker compose up -d
```

Сброс использует БД из текущего `DATABASE_URL` контейнера. Внешние приложения, работающие с этой БД, также должны быть остановлены. Обычные перезапуск и повторный seed ничего не сбрасывают.

## Подключение DBeaver

Создайте подключение PostgreSQL:

| Настройка | Значение по умолчанию |
|---|---|
| Host | localhost |
| Port | 5433 |
| Database | hotel |
| Username | hotel |
| Password | hotel_dev_password |
| SSL | Disable для локального Compose |

Нажмите Test Connection, при необходимости разрешите DBeaver скачать JDBC-драйвер. Таблицы расположены в `hotel → Schemas → public → Tables`. Для просмотра точного UTC-времени можно выполнить `SET TIME ZONE 'UTC'` в SQL-сессии DBeaver.

Если меняли `.env`, используйте собственные значения. Изменение POSTGRES_USER/PASSWORD/DB не переинициализирует существующий PostgreSQL volume; для действующей БД нужен её текущий пароль. API и БД публикуются только на loopback-интерфейсе компьютера.

## Локальная разработка без контейнера API

Python 3.12+, запущенный PostgreSQL с миграциями. Через uv:

```powershell
Copy-Item .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run python -m app.scripts.seed
uv run uvicorn app.main:app --reload
```

Worker в Docker уже работает; второй экземпляр для разработки не обязателен. `requirements.lock` экспортирован из `uv.lock` для установки внутри Docker. После изменения зависимостей обновляйте оба файла через `uv lock` и `uv export --format requirements-txt --no-hashes --no-emit-project -o requirements.lock`.

## Настройки

`DATABASE_URL`, `JWT_SECRET` (не меньше 32 символов), `SEED_PASSWORD`; внутренние defaults: `JWT_MINUTES=60`, `HOLD_MINUTES=30`, `WORKER_INTERVAL_SECONDS=5`. Изменение длительностей означает отклонение от стандартного контракта проекта. Compose использует согласованные 60/30 минут.

Для портов можно задать `API_PORT`, `POSTGRES_PORT`. В пароле PostgreSQL внутри URL используйте URL-кодирование специальных символов. Значения по умолчанию предназначены для локального учебного запуска.

## Проверка реализации

При разработке выполнены сборка и запуск Compose, применение миграции и `alembic check`, HTTP-проверка основных операций, идемпотентности, возврата и разграничения доступа. На PostgreSQL проверены точное равенство `now == expires_at`, ожидание блокировки через дедлайн и конкурентные бронирования, платежи и отмена. Временные проверки выполнялись без сохранения QA-набора в проекте. Команда сброса возвращает БД к seed.
