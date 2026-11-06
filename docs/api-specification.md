# Спецификация REST API

База: `http://localhost:8000/api/v1`. Swagger: `http://localhost:8000/docs`. Точная машиночитаемая схема со всеми полями: `/openapi.json`. Все 29 операций перечислены ниже. UUID в примерах заменяются реальными ID из ответов API. Даты примеров также заменяются актуальными UTC-датами.

## Общий контракт

JSON-тела: `Content-Type: application/json`. Защищённые операции требуют `Authorization: Bearer <access_token>`. Login использует JSON, не OAuth2 form. В Swagger сначала выполнить login, затем вставить токен без префикса Bearer в Authorize.

Роли: `user`, `admin`. Обозначение «владелец» включает admin только для его собственных бронирований. Admin имеет право читать все бронирования/платежи и отменять чужие бронирования; создавать и симулировать чужие платежи не может.

Даты: `YYYY-MM-DD`. Timestamps: ISO 8601 с UTC-смещением. Деньги и рейтинг в ответах — десятичные строки. Модели JSON отклоняют неизвестные поля. GET/DELETE не требуют тела; операции без описанной модели тела не используют его.

Списки: `limit=20` (1–100), `offset=0` (≥0). `sort=field` — возрастание, `sort=-field` — убывание. При равенстве используется UUID по возрастанию. Неизвестное поле сортировки — 422.

```json
{"items": [], "total": 0, "limit": 20, "offset": 0}
```

Ошибки:

```json
{
  "error": {
    "code": "ROOM_NOT_AVAILABLE",
    "message": "Room is occupied for these dates.",
    "details": [],
    "request_id": "acb6569c-fda0-4ebf-a2d1-5d1569022791"
  }
}
```

`message` предназначен для человека и может уточняться; стабильный контракт — HTTP-статус и `code`. При валидации `details` содержит объекты `field`, `message`, `type`. Тела с паролями и токенами в ошибках не отражаются. Каждый ответ содержит серверный `X-Request-ID`; для 401 также `WWW-Authenticate: Bearer`.

## Авторизация и профиль

| Метод и путь | Доступ | Тело / параметры | Успех |
|---|---|---|---|
| POST `/auth/register` | Публичный | Register | 201 User |
| POST `/auth/login` | Публичный | email, password | 200 Token |
| GET `/users/me` | Авторизованный | — | 200 User |
| PATCH `/users/me` | Авторизованный | Любые из email, name, phone; хотя бы одно | 200 User |

Register:

```json
{"email":"new.user@example.com","password":"HotelDemo123!","name":"New User","phone":"+79991234567"}
```

Login:

```json
{"email":"alice@example.com","password":"HotelDemo123!"}
```

Token:

```json
{"access_token":"<JWT>","token_type":"bearer","expires_in":3600}
```

User:

```json
{
  "id":"e2e186d6-7682-466a-812e-b6367d9e4343",
  "email":"new.user@example.com",
  "name":"New User",
  "phone":"+79991234567",
  "role":"user",
  "is_active":true,
  "created_at":"2026-10-31T10:00:00Z",
  "updated_at":"2026-10-31T10:00:00Z"
}
```

Ограничения учётных данных для регистрации и входа (правила email действуют и для PATCH профиля):

| Правило | Email | Пароль |
|---|---|---|
| Символы | Только ASCII, с проверкой формата адреса без отображаемого имени | Печатные ASCII U+0021–U+007E: латинские буквы, цифры, пунктуация |
| Длина | До 254 символов после обрезки | 10–128 символов |
| Пробелы | Только обычные крайние пробелы U+0020 обрезаются; внутренние запрещены | Запрещены в любом месте |
| Регистр | Приводится к нижнему | Сохраняется и имеет значение |
| Кириллица, иероглифы, emoji | Запрещены | Запрещены |
| Табуляция, переносы строк, управляющие и невидимые символы | Запрещены даже по краям исходной строки | Запрещены |

Пароль не обрезается и не преобразуется. Обязательного сочетания букв, цифр и спецсимволов нет. Нарушение правил — 422 `VALIDATION_ERROR`; `error.details[].field` указывает `body.email` или `body.password`. При нарушении нескольких правил ответ может содержать несколько деталей.

Прочие ограничения: имя 1–100, телефон `+` необязателен, 7–15 цифр. PATCH допускает `phone:null`, но не null для имени/email. При дубликате email — 409 `EMAIL_EXISTS`; login при валидных по формату, но неверных данных или деактивации — 401 `INVALID_CREDENTIALS`.

## Отели

| Метод и путь | Доступ | Тело / параметры | Успех |
|---|---|---|---|
| GET `/hotels` | Публичный | Пагинация, city, min_rating, max_rating, min_price, max_price, sort, include_archived | 200 Page[Hotel] |
| GET `/hotels/{hotel_id}` | Публичный | UUID | 200 Hotel |
| POST `/hotels` | Admin | HotelInput | 201 Hotel |
| PUT `/hotels/{hotel_id}` | Admin | Полный HotelInput | 200 Hotel |
| DELETE `/hotels/{hotel_id}` | Admin | UUID | 204 без тела |

HotelInput:

```json
{"name":"Baikal Hotel","city":"Irkutsk","address":"10 Central Street","description":"City hotel","rating":"4.5"}
```

Hotel содержит эти поля и `id`, `is_archived`, `created_at`, `updated_at`. Все поля HotelInput обязательны, пустое description разрешено. Рейтинг 0–5 с одним десятичным знаком.

Город сравнивается целиком без учёта регистра, с удалением крайних пробелов. Рейтинг и цена фильтруются включительно. Диапазон цен отбирает отель, если существует хотя бы один неархивный номер с `is_available=true` в этом диапазоне. Это не поиск по свободным датам.

Сортировка: `name` (default), `rating`, `price`; price — минимальная цена такого активного номера, отели без цены идут последними. `include_archived=true` требует admin. Архивные детали доступны admin, публично — 404. Архивирование с действующими бронями — 409 `ACTIVE_BOOKINGS_EXIST`. Повтор DELETE — 204.

## Номера

| Метод и путь | Доступ | Тело / параметры | Успех |
|---|---|---|---|
| GET `/hotels/{hotel_id}/rooms` | Публичный | Пагинация, min_price, max_price, min_capacity, type, sort, include_archived | 200 Page[Room] |
| GET `/rooms/{room_id}` | Публичный | UUID | 200 Room |
| POST `/hotels/{hotel_id}/rooms` | Admin | RoomInput | 201 Room |
| PUT `/rooms/{room_id}` | Admin | Полный RoomInput | 200 Room |
| PATCH `/rooms/{room_id}/availability` | Admin | is_available | 200 Room |
| DELETE `/rooms/{room_id}` | Admin | UUID | 204 без тела |
| GET `/rooms/{room_id}/availability` | Публичный | check_in, check_out, guests — обязательны | 200 Availability |

RoomInput:

```json
{"room_number":"201","type":"double","capacity":2,"price_per_night":"3000.00"}
```

Room содержит эти поля и `id`, `hotel_id`, `is_available`, `is_archived`, `created_at`, `updated_at`. Новый номер доступен для бронирования. room_number 1–20, capacity — целое 1–10, price_per_night 0.01–9999999999.99. Типы: single, double, twin, family, suite.

PATCH availability:

```json
{"is_available":false}
```

Сортировка номеров: `price` (default), `capacity`, `room_number` (лексикографически). Диапазон цен включителен; min_capacity 1–10. Архивный родитель скрывает номера от публичных запросов. Неархивные отключённые номера остаются в списке.

Пример запроса доступности:

```http
GET /api/v1/rooms/<room_id>/availability?check_in=2026-11-10&check_out=2026-11-12&guests=2
```

```json
{
  "room_id":"47bddacb-086b-4d9c-ab8d-73a46c4b2220",
  "check_in":"2026-11-10","check_out":"2026-11-12","guests":2,
  "available":true,"reason":null,"nights":2,"total_price":"6000.00","currency":"RUB"
}
```

При недоступности — 200, `available:false`, причина `ROOM_DISABLED`, `CAPACITY_EXCEEDED` или `ROOM_NOT_AVAILABLE`. При ошибочных датах — 422; отсутствующий/архивный номер — 404. GET не резервирует номер.

## Бронирования

| Метод и путь | Доступ | Тело / параметры | Успех |
|---|---|---|---|
| POST `/bookings` | Авторизованный | BookingInput, заголовок Idempotency-Key | 201 Booking |
| GET `/bookings` | Авторизованный | Пагинация, status, hotel_id, user_id (только admin), check_in_from, check_in_to, sort | 200 Page[Booking] |
| GET `/bookings/{booking_id}` | Владелец / admin | UUID | 200 Booking |
| PATCH `/bookings/{booking_id}/cancel` | Владелец / admin | Без тела | 200 Booking |

Создание:

```http
POST /api/v1/bookings
Authorization: Bearer <JWT>
Content-Type: application/json
Idempotency-Key: booking-001
```

```json
{"room_id":"47bddacb-086b-4d9c-ab8d-73a46c4b2220","check_in":"2026-11-10","check_out":"2026-11-12","guests":2}
```

Booking:

```json
{
  "id":"92d2ec5a-5eb1-45be-ad38-a03c4f3da210",
  "user_id":"e2e186d6-7682-466a-812e-b6367d9e4343",
  "room_id":"47bddacb-086b-4d9c-ab8d-73a46c4b2220",
  "check_in":"2026-11-10","check_out":"2026-11-12","guests":2,
  "status":"pending_payment","price_per_night":"3000.00","total_price":"6000.00",
  "currency":"RUB","expires_at":"2026-10-31T10:30:00Z",
  "created_at":"2026-10-31T10:00:00Z","updated_at":"2026-10-31T10:00:00Z"
}
```

Статусы: pending_payment, confirmed, cancelled, expired, completed. Сортировка: `-created_at` (default), created_at, check_in, total_price. Даты фильтра заезда включительны. Фильтрация по несуществующему hotel_id/user_id даёт пустой список, если фильтр разрешён по роли.

Идемпотентность: 1–128 символов `[A-Za-z0-9._:-]`. Повтор с одинаковым валидным телом возвращает исходный снимок с 201 и `Idempotency-Replayed:true` даже после смены статуса; `Location` указывает на GET актуальной брони. Другое тело с тем же ключом — 409. Отсутствующий/невалидный ключ — 422. После отмены/истечения новая бронь требует нового ключа.

Отмена до даты заезда атомарно освобождает номер и возвращает всю тестовую оплату. Повторная отмена — 200; истёкшая/завершённая бронь — 409; отмена в день заезда — 409. Подробные приоритеты — в таблице ошибок и requirements.md.

## Тестовые платежи

| Метод и путь | Доступ | Тело | Успех |
|---|---|---|---|
| POST `/bookings/{booking_id}/payments` | Владелец | Не требуется | 201 Payment |
| GET `/payments/{payment_id}` | Владелец / admin | Не требуется | 200 Payment |
| POST `/payments/{payment_id}/simulate-success` | Владелец | Не требуется | 200 Payment |
| POST `/payments/{payment_id}/simulate-failure` | Владелец | FailureInput | 200 Payment |

FailureInput — JSON-объект обязателен; reason необязателен, по умолчанию `Simulated decline`, 1–250 символов:

```json
{"reason":"Simulated insufficient funds"}
```

Payment:

```json
{
  "id":"867c3167-c373-4d2f-a8a5-b0f28370873e",
  "booking_id":"92d2ec5a-5eb1-45be-ad38-a03c4f3da210",
  "amount":"6000.00","currency":"RUB","status":"pending","failure_reason":null,
  "created_at":"2026-10-31T10:01:00Z","updated_at":"2026-10-31T10:01:00Z"
}
```

Статусы: pending, succeeded, failed, cancelled, refunded. Создание повторного платежа не идемпотентно: пока есть pending, возвращается 409; после failed создаётся новый ID, если бронь ещё платёжная. Срок бронирования не продлевается. Повтор симуляции — 409, повторного списания нет. Дедлайн проверяется при `now >= expires_at`, после получения блокировок.

## Администрирование пользователей

| Метод и путь | Доступ | Параметры / тело | Успех |
|---|---|---|---|
| GET `/admin/users` | Admin | Пагинация, role, is_active, sort | 200 Page[User] |
| GET `/admin/users/{user_id}` | Admin | UUID | 200 User |
| PATCH `/admin/users/{user_id}` | Admin | role и/или is_active | 200 User |

Сортировка: `created_at` (default), `email`. Пустой PATCH и null запрещены.

```json
{"role":"user","is_active":false}
```

Деактивация сохраняет бронирования и платежи. Запросы, прошедшие проверку активности до изменения, могут завершиться. Последний активный admin защищён от отключения и понижения роли: 409 `LAST_ACTIVE_ADMIN`.

## Health

| Метод и путь | Успех | Ошибка |
|---|---|---|
| GET `/health/live` | 200 `{"status":"alive"}` | — |
| GET `/health/ready` | 200 `{"status":"ready"}` | 503, если БД/миграции не готовы |

## Основные ошибки и ограничения

Все ошибки используют единый envelope, приведённый выше.

| HTTP | code | Условие |
|---|---|---|
| 401 | UNAUTHORIZED | Нет корректного Bearer JWT, JWT истёк, пользователь отсутствует/отключён |
| 401 | INVALID_CREDENTIALS | Login с неверным паролем/email или отключённой учётной записью |
| 403 | FORBIDDEN | Административная операция, архивный список без admin, user_id-фильтр без admin |
| 404 | NOT_FOUND | Отсутствующий ресурс, чужая бронь/платёж, скрытый архивный ресурс |
| 405 | METHOD_NOT_ALLOWED | HTTP-метод не поддерживается |
| 409 | EMAIL_EXISTS | Дубликат нормализованного email |
| 409 | ROOM_NUMBER_EXISTS | Дубликат номера комнаты в отеле |
| 409 | ROOM_DISABLED | Создание брони в отключённом номере |
| 409 | CAPACITY_EXCEEDED | Гостей больше вместимости при создании брони |
| 409 | ROOM_NOT_AVAILABLE | Пересечение блокирующих интервалов |
| 409 | IDEMPOTENCY_KEY_REUSED | Тот же ключ с другим валидированным запросом |
| 409 | PAYMENT_ALREADY_PENDING | Создание платежа при существующем pending |
| 409 | BOOKING_EXPIRED | Создание/симуляция платежа после истечения брони |
| 409 | BOOKING_NOT_PAYABLE | Создание/симуляция платежа для confirmed, cancelled, completed |
| 409 | PAYMENT_STATE_CONFLICT | Симуляция непредусмотренного состояния платежа при pending_payment-брони |
| 409 | BOOKING_STATE_CONFLICT | Отмена expired или completed |
| 409 | CANCELLATION_CLOSED | Отмена pending_payment/confirmed в день заезда или позднее |
| 409 | ACTIVE_BOOKINGS_EXIST | Архивирование номера/отеля с блокирующими бронями |
| 409 | CAPACITY_IN_USE | Уменьшение вместимости нарушает действующую бронь |
| 409 | RESOURCE_ARCHIVED | Изменение архивного объекта или создание номера в архивном отеле |
| 409 | LAST_ACTIVE_ADMIN | Отключение/понижение последнего активного admin |
| 409 | CONCURRENT_OPERATION | Тайм-аут блокировки/SQL, deadlock, ошибка сериализации; допустим повтор |
| 409 | RESOURCE_CONFLICT | Иное нарушение ограничения целостности БД |
| 422 | VALIDATION_ERROR | Неверный JSON/UUID/тип/enum, лишние поля модели, обязательное поле отсутствует, границы значений, длительность вне 1–14 ночей, неверный Idempotency-Key |
| 422 | PAST_CHECK_IN | Заезд раньше UTC-даты решения |
| 422 | INVALID_FILTER_RANGE | Минимальная граница фильтра больше максимальной |
| 422 | INVALID_SORT | Неизвестное поле сортировки |
| 503 | DATABASE_NOT_READY | Health ready не может проверить БД/таблицу миграций |
| 503 | SCHEMA_NOT_READY | Версия миграции не соответствует приложению |
| 503 | DATABASE_UNAVAILABLE | БД временно недоступна при обычном запросе |
| 500 | INTERNAL_ERROR | Непредвиденная внутренняя ошибка без технических подробностей в ответе |

Порядок бизнес-проверок после успешной валидации/авторизации:

1. Создание брони: ключ и совпадение запроса → наличие номера → актуализация → прошедшая дата → архивность → доступность → вместимость → пересечение.
2. Оплата: наличие и владение → актуализация → истечение → платёжность брони → состояние/наличие pending-платежа.
3. Отмена: наличие и доступ → актуализация → повтор отмены → допустимость состояния → дата отмены.

Если одновременно нарушены независимые правила схемы и авторизации, порядок их обнаружения FastAPI не является частью бизнес-контракта; ответ всё равно имеет единый формат.
