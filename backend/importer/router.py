"""Импорт Excel: загрузка клиентов и срезов, отчёт об ошибках по строкам.

Заглушка скелета: рабочие функции — спринт 3 (Р-04, H-01).
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["importer"])


@router.post("/imports/clients")
def import_clients() -> None:
    """Загрузка файла «Клиенты»: предпросмотр, отчёт об ошибках, загрузка."""
    raise HTTPException(status_code=501, detail="модуль импорта в разработке (спринт 3)")


@router.post("/imports/snapshots")
def import_snapshots() -> None:
    """Загрузка файла среза: сопоставление по коду КЦР, срезы не перезаписываются."""
    raise HTTPException(status_code=501, detail="модуль импорта в разработке (спринт 3)")
