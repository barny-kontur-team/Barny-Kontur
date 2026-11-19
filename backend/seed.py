"""Обезличенные пользователи и 20 контрольных клиентов для локального демо.

Запуск в контейнере:  docker compose exec api python -m seed
Локально:             cd backend && python -m seed
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import select

from calls.service import CONTACT_CALL, STAGES, STAGE_CLOSED
from db import SessionLocal, init_db
from dynamics.service import recalculate_client
from models import AppUser, Client, Communication, DocumentSnapshot, ImportBatch, WorkCycle

DEMO_USERS = (
    {"full_name": "Елена Соколова", "login": "admin@example.test", "role": "ADMIN"},
    {"full_name": "Алексей Смирнов", "login": "operator@example.test", "role": "OPERATOR"},
    {"full_name": "Мария Орлова", "login": "operator2@example.test", "role": "OPERATOR"},
    {"full_name": "Иван Волков", "login": "operator3@example.test", "role": "OPERATOR"},
)

# Название, текущий остаток и всего, предыдущий остаток и всего,
# номер оператора (0 — без ответственного), индекс этапа, обещанный срок.
DEMO_CLIENTS = (
    ("Альфа", 2, 30, (3, 25), 1, 1, "09-30"),
    ("Бета", 1, 25, (2, 20), 2, 1, "09-25"),
    ("Гамма", 1, 10, (2, 8), 1, 3, "10-15"),
    ("Дельта", 3, 14, (3, 12), 3, 3, "10-01"),
    ("Эпсилон", 5, 26, (6, 22), 2, 4, None),
    ("Зета", 0, 100, (2, 100), 0, 0, None),
    ("Эта", 8, 50, (9, 50), 3, 3, None),
    ("Тета", 0, 12, (0, 12), 1, 5, None),
    ("Йота", 1, 20, (2, 20), 3, 1, "09-30"),
    ("Каппа", 4, 25, (5, 20), 1, 2, "10-31"),
    ("Лямбда", 7, 10, (6, 9), 0, 0, None),
    ("Мю", 0, 0, (0, 10), 2, 5, None),
    ("Ню", 4, 20, None, 2, 1, "04-30"),
    ("Кси", 5, 100, (4, 100), 0, 0, None),
    ("Омикрон", 0, 0, (0, 0), 0, 0, None),
    ("Пи", 3, 12, None, 0, 0, None),
    ("Ро", 6, 20, None, 2, 2, "10-25"),
    ("Сигма", 1, 40, None, 0, 0, None),
    ("Тау", 8, 16, None, 0, 0, None),
    ("Ипсилон", 4, 10, None, 3, 2, "10-22"),
)
DEMO_TYPE = "Демо H-08"
CALL_DATES = {1: "09-05", 2: "09-08", 3: "09-22", 4: "09-10", 7: "08-12",
              8: "06-20", 9: "09-12", 10: "09-15", 12: "07-02", 13: "04-10",
              17: "10-01", 20: "10-18"}


def demo_date(month_day: str) -> date:
    return date.fromisoformat("2026-" + month_day)


def seed() -> tuple[int, int]:
    """Добавляет отсутствующие записи набора в одной транзакции."""
    init_db()
    with SessionLocal() as db:
        codes = [str(1000000 + index) for index in range(1, len(DEMO_CLIENTS) + 1)]
        existing = {client.kcr_code: client for client in db.scalars(
            select(Client).where(Client.kcr_code.in_(codes))
        )}
        skipped = []
        for index, code in enumerate(codes, 1):
            client = existing.get(code)
            if client and (client.client_type != DEMO_TYPE or client.inn != str(9900000000 + index)):
                skipped.append(code)
        if skipped:
            raise ValueError("Коды КЦР уже заняты другими клиентами: " + ", ".join(skipped))

        users = []
        new_users = 0
        for item in DEMO_USERS:
            user = db.scalar(select(AppUser).where(AppUser.login == item["login"]))
            if user is None:
                user = AppUser(password_hash="demo-no-auth", is_active=True, **item)
                db.add(user)
                new_users += 1
            elif user.role != item["role"] or user.password_hash != "demo-no-auth" or not user.is_active:
                raise ValueError("Тестовый логин уже занят или отключён: " + item["login"])
            users.append(user)
        db.flush()

        new_rows = [(index, code, row) for index, (code, row) in enumerate(zip(codes, DEMO_CLIENTS), 1)
                    if code not in existing]
        if new_rows:
            previous_count = sum(row[3] is not None for _, _, row in new_rows)
            batches = []
            for name, count in (("Демо H-08 · S004", previous_count), ("Демо H-08 · S005", len(new_rows))):
                batch = ImportBatch(file_name=name, import_type="SNAPSHOTS", status="OK",
                                    created_count=count, error_count=0)
                db.add(batch)
                batches.append(batch)
            db.flush()
            created = []
            for index, code, (name, missing, total, previous, owner, stage, due) in new_rows:
                client = Client(kcr_code=code, inn=str(9900000000 + index), client_type=DEMO_TYPE,
                                organization_name=f"ООО «{name}-Тест»", is_do_not_work=index == 7,
                                connection_date=demo_date("06-01" if index in (3, 16) else "01-10"))
                db.add(client)
                db.flush()
                snapshots = [(batches[1], "III кв. 2026", "10-20", (missing, total))]
                if previous is not None:
                    snapshots.insert(0, (batches[0], "II кв. 2026", "08-17", previous))
                for batch, period, day, (remaining, all_documents) in snapshots:
                    db.add(DocumentSnapshot(client_id=client.id, import_batch_id=batch.id,
                                            reporting_period=period, snapshot_date=demo_date(day),
                                            total_documents=all_documents, missing_documents=remaining))
                if owner:
                    call_day = CALL_DATES.get(index)
                    started = datetime.combine(demo_date(call_day or "09-25"), time(10))
                    cycle = WorkCycle(client_id=client.id, operator_id=users[owner].id,
                                      stage=STAGES[stage], started_at=started,
                                      closed_at=started if STAGES[stage] == STAGE_CLOSED else None)
                    db.add(cycle)
                    db.flush()
                    if call_day:
                        db.add(Communication(client_id=client.id, user_id=users[owner].id, cycle_id=cycle.id,
                                             contact_type=CONTACT_CALL, result="Дозвонились", created_at=started,
                                             comment="Передать оставшиеся документы" if due else "Уточнили статус документов",
                                             promised_date=demo_date(due) if due else None))
                created.append(client.id)
            db.flush()
            for client_id in created:
                recalculate_client(db, client_id)
        db.commit()
        return new_users, len(new_rows)


if __name__ == "__main__":
    try:
        users, clients = seed()
    except ValueError as exc:
        raise SystemExit(f"Демонабор не загружен. {exc}") from None
    print(f"Добавлено пользователей: {users}. Добавлено клиентов: {clients}.")
