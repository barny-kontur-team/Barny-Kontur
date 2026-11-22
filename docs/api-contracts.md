# Контракты API по текущему FastAPI-коду

Запуск: `PYTHONPATH=backend uvicorn main:app --app-dir backend --reload`. Интерактивный Swagger: [локальный /docs](http://127.0.0.1:8000/docs); OpenAPI JSON: [локальный /openapi.json](http://127.0.0.1:8000/openapi.json). Адрес доступен **только при запущенном сервере**, это не публичный URL.

| Метод и маршрут | Запрос | Успех (200) | Ошибки |
|---|---|---|---|
| `GET /health` | — | `{"status":"ok","db":"ok"}` или `"down"` | — |
| `POST /api/imports/clients` | multipart: `file` (`.xlsx`) | `{"created":2,"status":"OK"}` | `422` некорректный Excel; `409` код уже есть в БД |
| `POST /api/imports/snapshots` | multipart: `file` (`.xlsx`), `reporting_period` (строка), `snapshot_date` (`YYYY-MM-DD`) | `{"created":2,"recalculated_clients":2,"status":"OK"}` | `422` ошибки файла/периода; `409` повтор даты среза |
| `GET /api/clients` | — | `{"clients":[...]}`: ID БД, код КЦР, реквизиты, история, `last`, `previous`, `last_closed_stage` (этап последнего закрытого цикла или `null`) | — |
| `GET /api/clients/{client_id}/dynamics` | path: **числовой ID БД**, не `kcr_code` | `client_id`, `kcr_code`, `first_appearance_date`, `history` | `404` клиент не найден |
| `GET /api/clients/{client_id}/calls` | path: ID | история коммуникаций, новые сверху | `404` клиент не найден |
| `GET /api/clients/{client_id}/work` | path: ID | кто ведёт сейчас: `cycle_id`, `operator_id`, `operator_name`, `stage` | `404` клиент не найден |
| `GET /api/work` | — | активные циклы: ответственный, этап, последний звонок | — |
| `GET /api/users` | — | пользователи для входа и выбора ответственного | — |
| `POST /api/clients/{client_id}/take` | path: ID; JSON `{"operator_id": 1, "takeover": false}` | `client_id`, `cycle_id`, `operator_id`, `operator_name`, `stage`, `started_at`, `takeover` | `404` клиент не найден; `409` клиента уже взял другой (без `takeover`); `422` пользователь не найден |
| `POST /api/clients/{client_id}/calls` | path: ID; JSON `operator_id`, `promised_date` (обязателен), `result`, `comment`, `contact_type`, `called_at`, `stage` | `201`: событие звонка | `404` клиент; `409` нет активного цикла или ведёт другой; `422` нет срока/неверный тип или этап |
| `POST /api/clients/{client_id}/summary` | path: ID | нет | `501` заглушка AI |
| `POST /api/clients/search` | — | нет | `501` заглушка AI |

**Звонки без авторизации.** Пока вход не сделан, `operator_id` передаётся в теле запроса. После появления авторизации его нужно брать из токена, а из тела убрать.

**Формат ошибок FastAPI**: `{"detail":"<причина>"}` для ручных `HTTPException`. Автоматическая проверка формы также может вернуть `422` со структурированным массивом `detail`.

## Примеры ошибок импорта (по `importer.validation` и `importer.router`)

**422 — дублирование кода внутри одного Excel:**

```json
{"detail":"Повтор кода КЦР в одном файле: 1000001"}
```

**422 — неизвестный клиент:**

```json
{"detail":"Строка 2: код КЦР 9999999 отсутствует в справочнике"}
```

**422 — неправильное количество:**

```json
{"detail":"Строка 2: непереданных документов больше общего количества"}
```

**422 — обязательный столбец отсутствует:**

```json
{"detail":"Отсутствуют обязательные столбцы: Не передано документов"}
```

**409 — повторная дата для клиента:**

```json
{"detail":"Срез на эту дату уже сохранён для клиентов: 1000001"}
```

Все приведённые тексты соответствуют существующим веткам обработки; точный код зависит от входных данных. **При ошибке одной строки весь Excel сейчас отклоняется**, частичной загрузки пока нет.

## Контракт истории динамики

Пример сокращённого ответа (данные **условные**, поля подтверждены кодом):

```json
{
  "client_id": 1,
  "kcr_code": "1000001",
  "first_appearance_date": "2026-01-20",
  "history": [{
    "snapshot_id": 1,
    "reporting_period": "I кв. 2026",
    "snapshot_date": "2026-01-20",
    "total_documents": 100,
    "missing_documents": 12,
    "missing_percent": 12.0,
    "dynamics_code": "NO_COMPARISON",
    "dynamics_name": "Нет сравнения",
    "is_novice": true,
    "show_novice_badge": true,
    "is_chronic": false,
    "category": "Нет сравнения"
  }]
}
```

`history` отсортирована по дате (при равенстве — по `id`). Коды: `NO_COMPARISON`, `ALL_TRANSFERRED`, `FIRST_APPEARED`, `DECREASING`, `FLAT_OR_GROWING`, `REAPPEARED`. `is_novice` не зависит от числа документов; `show_novice_badge = is_novice AND missing_documents > 0`. `category` — вычисляемая по приоритету метка; отдельной колонкой в БД не хранится.

В текущем коде для POST импорта и GET динамики **не подключена авторизация по ролям**. Не использовать эту документацию как подтверждение готовности механизма доступа.
