"""Динамика: три признака по клиенту — изменение между срезами, «новичок»,
«хронический» (модель Б, Р-02, H-02).

Заглушка скелета: расчёт в сервисе — спринт 3. Правила уже реализованы и
проверены в scripts/h02/features.py — оттуда их перенесёт dynamics/.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["dynamics"])


@router.get("/clients/{client_id}/dynamics")
def client_dynamics(client_id: int) -> None:
    """Признаки клиента по срезам (история, не перезаписывается)."""
    raise HTTPException(status_code=501, detail="модуль динамики в разработке (спринт 3)")
