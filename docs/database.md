# Структура БД: фактические таблицы SQLAlchemy

Источник истины — `backend/models.py`, сверено с приложенной книгой «Схема данных для спецификации основные сущности.xlsx» (листы «01 Обзор БД», «02 Поля таблиц», «03 Связи», «04 Excel → БД»). В спецификации перечислено **9** логических сущностей; физическое имя `USER` заменено на `app_user`. Здесь перечислены **все колонки актуального кода**, не только предполагаемые поля шаблона.

| Таблица | Поля (без сокращения) | Откуда данные / состояние реализации |
|---|---|---|
| `client` | `id`, `kcr_code`, `inn`, `kpp`, `organization_name`, `client_type`, `connection_date`, `phone`, `email`, `is_blocked`, `is_do_not_work`, `first_appearance_date` | `POST /api/imports/clients`: код, ИНН, КПП, название, тип, дата подключения, «не включать в работу». `first_appearance_date` рассчитывается H-02; `phone`, `email`, `is_blocked` сейчас **не заполняются** данным эндпоинтом. |
| `import_batch` | `id`, `file_name`, `import_type`, `imported_at`, `status`, `created_count`, `error_count` | Создаётся успешными вызовами импорта `clients`/`snapshots`. Неудачные импорты не фиксируются как записи пакета в текущем коде. |
| `document_snapshot` | `id`, `client_id`, `import_batch_id`, `reporting_period`, `snapshot_date`, `total_documents`, `missing_documents`, `missing_percent`, `dynamics_code`, `is_novice`, `is_chronic` | Excel-срез + параметры POST (период, дата) + FK на `client`, `import_batch`. Расчётные поля записывает `dynamics.service`. |
| `app_user` | `id`, `full_name`, `login`, `password_hash`, `role`, `is_active` | Проектная таблица сотрудников; API управления/ввода пользователей **пока нет**. |
| `work_cycle` | `id`, `client_id`, `operator_id`, `stage`, `started_at`, `closed_at`, `close_reason` | Цикл работы оператора; функции `calls` **пока 501**, из импорта не создаётся. Активный `stage` читается расчётом H-02. |
| `communication` | `id`, `client_id`, `cycle_id`, `user_id`, `contact_type`, `result`, `comment`, `promised_date`, `created_at` | История звонков/писем, обещанный срок; запись через API **пока не реализована**. |
| `task` | `id`, `client_id`, `cycle_id`, `assigned_user_id`, `task_type`, `due_at`, `status` | Запланированное действие; запись через API **пока не реализована**. |
| `claim` | `id`, `client_id`, `cycle_id`, `claim_number`, `claim_date`, `incident_number`, `status` | Претензия; запись через API **пока не реализована**. |
| `sanction` | `id`, `claim_id`, `sanction_type`, `status`, `applied_date` | Санкция по претензии; запись через API **пока не реализована**. |

## Ключи и связи

- `client.kcr_code` — уникален, `inn` **не** уникален.
- `document_snapshot.client_id → client.id`, `.import_batch_id → import_batch.id`; ограничение UNIQUE `(client_id, reporting_period, snapshot_date)` и CHECK `missing_documents >= 0`, `missing_documents <= total_documents` при известном total.
- `work_cycle.client_id → client.id`, `.operator_id → app_user.id`; частичный уникальный индекс не допускает более одного активного цикла клиента (`closed_at IS NULL`).
- `communication`: ссылки на `client`, опционально `work_cycle`, обязательно `app_user`.
- `task`: ссылки на `client`, опционально `work_cycle`, опционально назначенного `app_user`.
- `claim`: ссылки на `client`, опционально `work_cycle`; `sanction.claim_id → claim.id`.
- Первичные ключи во всех таблицах — `id`; создаются через `db.init_db() / Base.metadata.create_all()`. Миграции Alembic пока не настроены.

## Отличия от приложенной книги/логической схемы

1. В коде `USER` → `app_user` (в PostgreSQL `user` конфликтует с ключевым словом).
2. В `client` дополнительно `first_appearance_date`; в `document_snapshot` — `is_novice`, `is_chronic` (модель Б, ADR-0002).
3. Книга описывает потенциальное сопоставление Excel → БД; **фактический импорт** сейчас заполняет только подмножество полей (`phone/email/is_blocked` не перенесены), а строки звонков/задач/претензий не импортируются.
4. В Excel заказчика H-01 могут отсутствовать коды КЦР; текущий backend ожидает именно `Код КЦР` и такие исходники без адаптации не принимает.
5. Формат отчётного периода поступает из формы API и сохраняется строкой (`I кв. 2026` либо `2026-Q1`), не из самого Excel.
