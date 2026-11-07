"""Точка входа API: FastAPI, /health, подключение модулей-заглушек.

Модули (importer, dynamics, calls, ai) пока возвращают 501 — рабочие функции
в спринте 3 (см. спецификацию архитектуры, раздел «Скелет решения»).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from calls.router import router as calls_router
from ai.router import router as ai_router
from config import settings
from db import check_db, init_db
from dynamics.router import router as dynamics_router
from importer.router import router as importer_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # создаёт таблицы, если их нет
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.include_router(importer_router, prefix="/api")
app.include_router(dynamics_router, prefix="/api")
app.include_router(calls_router, prefix="/api")
app.include_router(ai_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    """Проверка «сервер жив» + пинг базы."""
    return {"status": "ok", "db": check_db()}
