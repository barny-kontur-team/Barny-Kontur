"""Подключение к базе и создание таблиц.

Схема БД — models.py (по спецификации «Схема данных», 9 сущностей).
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Создаёт таблицы, если их нет (для MVP достаточно; миграции — при необходимости)."""
    import models  # noqa: F401  — регистрирует таблицы в Base.metadata

    Base.metadata.create_all(engine)


def check_db() -> str:
    """Пинг базы для /health: 'ok' или 'down'."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:  # noqa: BLE001 — health не должен падать
        return "down"
