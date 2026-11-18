"""Демо-пользователи для звонков.

Входа и ролей пока нет, но эндпоинтам звонков нужен `operator_id`, поэтому
двух пользователей надо создать заранее. Пароль — заглушка: авторизация
появится отдельной задачей.

Запуск в контейнере:  docker compose exec api python -m seed
Локально:             cd backend && python -m seed
"""
from __future__ import annotations

from sqlalchemy import select

from db import SessionLocal, init_db
from models import AppUser

DEMO_USERS = (
    {"full_name": "Елена Соколова", "login": "admin@example.test", "role": "ADMIN"},
    {"full_name": "Алексей Смирнов", "login": "operator@example.test", "role": "OPERATOR"},
    {"full_name": "Мария Орлова", "login": "operator2@example.test", "role": "OPERATOR"},
)


def seed() -> list[str]:
    """Создаёт демо-пользователей, если их ещё нет. Возвращает логины новых."""
    init_db()
    created: list[str] = []
    with SessionLocal() as db:
        for item in DEMO_USERS:
            exists = db.scalar(select(AppUser).where(AppUser.login == item["login"]))
            if exists is not None:
                continue
            db.add(AppUser(password_hash="demo-no-auth", is_active=True, **item))
            created.append(item["login"])
        db.commit()
    return created


if __name__ == "__main__":
    new = seed()
    print("созданы: " + ", ".join(new) if new else "пользователи уже есть")
