# Схема PostgreSQL

PostgreSQL 17, SQLAlchemy 2.x, Alembic. Начальная ревизия: `0001_initial`. Миграция содержит зафиксированный DDL и не импортирует текущие модели. `btree_gist` создаётся миграцией для exclusion constraint.

Все `id` — UUID PK, генерируются приложением. В seed UUID воспроизводимы. Все timestamps — `TIMESTAMP WITH TIME ZONE`; соединения используют UTC. Внешние ключи без каскадного удаления: история сохраняется.

## users

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| email | VARCHAR(254) | NOT NULL, UNIQUE uq_users_email; приложение нормализует регистр |
| password_hash | VARCHAR(255) | NOT NULL, Argon2 |
| name | VARCHAR(100) | NOT NULL |
| phone | VARCHAR(25) | NULL допустим |
| role | VARCHAR(10) | NOT NULL, CHECK user/admin |
| is_active | BOOLEAN | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now(); обновляется ORM |

## hotels

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(150) | NOT NULL |
| city | VARCHAR(100) | NOT NULL, индекс |
| address | VARCHAR(250) | NOT NULL |
| description | TEXT | NOT NULL |
| rating | NUMERIC(2,1) | NOT NULL, CHECK 0–5 |
| is_archived | BOOLEAN | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

## rooms

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| hotel_id | UUID | NOT NULL, FK hotels.id, индекс |
| room_number | VARCHAR(20) | NOT NULL |
| type | VARCHAR(20) | CHECK single/double/twin/family/suite |
| capacity | INTEGER | NOT NULL, CHECK 1–10 |
| price_per_night | NUMERIC(12,2) | NOT NULL, CHECK > 0 |
| is_available | BOOLEAN | NOT NULL; разрешение новых бронирований |
| is_archived | BOOLEAN | NOT NULL |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

UNIQUE `uq_room_number(hotel_id, room_number)`. Номера комнат сравниваются с учётом регистра.

## bookings

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | NOT NULL, FK users.id, индекс |
| room_id | UUID | NOT NULL, FK rooms.id, индекс |
| check_in, check_out | DATE | NOT NULL, CHECK разность 1–14 |
| guests | INTEGER | NOT NULL, CHECK 1–10 |
| status | VARCHAR(25) | NOT NULL, CHECK пяти статусов, индекс |
| price_per_night | NUMERIC(12,2) | NOT NULL, снимок цены, CHECK > 0 |
| total_price | NUMERIC(14,2) | NOT NULL, CHECK равен price_per_night × число ночей |
| currency | VARCHAR(3) | NOT NULL, CHECK RUB |
| expires_at | TIMESTAMPTZ | NOT NULL, индекс |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

```sql
CONSTRAINT no_overlapping_bookings EXCLUDE USING gist (
  room_id WITH =,
  daterange(check_in, check_out, '[)') WITH &&
) WHERE (status IN ('pending_payment', 'confirmed'))
```

Условие использует сохранённое состояние, не `now()`. Worker и операции API переводят истёкшие брони в `expired` под блокировками перед новой бронью. Это позволяет надёжно использовать индексируемое ограничение PostgreSQL.

## payments

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| booking_id | UUID | NOT NULL, FK bookings.id, индекс |
| amount | NUMERIC(14,2) | NOT NULL, CHECK > 0 |
| currency | VARCHAR(3) | NOT NULL, CHECK RUB |
| status | VARCHAR(15) | NOT NULL, CHECK pending/succeeded/failed/cancelled/refunded |
| failure_reason | VARCHAR(250) | NULL допустим |
| created_at, updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

Частичные UNIQUE-индексы:

- `uq_payment_pending(booking_id) WHERE status = 'pending'`.
- `uq_payment_charged(booking_id) WHERE status IN ('succeeded','refunded')`.

Возвращённая оплата также занимает уникальное место успешного списания: после возврата второе списание для этой брони недопустимо.

## idempotency_records

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | NOT NULL, FK users.id |
| operation | VARCHAR(50) | NOT NULL; create_booking |
| key | VARCHAR(128) | NOT NULL |
| request_hash | VARCHAR(64) | NOT NULL, SHA-256 канонических валидированных полей |
| response_status | INTEGER | NOT NULL; 201 |
| response_body | JSONB | NOT NULL, исходный снимок |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |

UNIQUE `uq_idempotency(user_id, operation, key)`. Бронь и снимок сохраняются в одной транзакции. Advisory lock сериализует даже запросы, для которых запись ключа ещё не создана. Не удаляются автоматически.

## booking_status_history / payment_status_history

Одинаковые общие поля:

| Поле | Тип | Ограничение / смысл |
|---|---|---|
| id | UUID | PK |
| booking_id / payment_id | UUID | NOT NULL, FK соответствующего ресурса, индекс |
| from_status | VARCHAR(25) | NULL только для создания |
| to_status | VARCHAR(25) | NOT NULL |
| reason | VARCHAR(250) | NOT NULL |
| actor_id | UUID | FK users.id, NULL для системного перехода |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT clock_timestamp() |

Приложение добавляет историю в транзакции изменения состояния. Таблицы не имеют HTTP-операций редактирования.

## Граница гарантий БД

Уникальность, положительные суммы, длительность, enum-подобные значения, FK и отсутствие пересечений защищены ограничениями БД. Вместимость относительно другой таблицы, сроки по текущему времени, права, граф переходов, соответствие суммы платежа брони и последний активный admin проверяются сервисами под блокировками. Прямое ручное изменение данных через SQL обходит эти сервисные правила.

Официальные справочники: [PostgreSQL Range Types](https://www.postgresql.org/docs/17/rangetypes.html), [btree_gist](https://www.postgresql.org/docs/17/btree-gist.html), [блокировки PostgreSQL](https://www.postgresql.org/docs/17/explicit-locking.html).
