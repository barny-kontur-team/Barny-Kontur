"""Звонки: этапы работы, события, претензии, взятие клиента в работу.

Заглушка скелета: рабочие функции — спринт 3.
Взятие в работу — один атомарный запрос к базе (Р-03, H-09).
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["calls"])


@router.post("/clients/{client_id}/take")
def take_client(client_id: int) -> None:
    """Взять клиента в работу: записать оператора, только если ответственного нет."""
    raise HTTPException(status_code=501, detail="модуль звонков в разработке (спринт 3)")


@router.post("/clients/{client_id}/calls")
def add_call(client_id: int) -> None:
    """Событие «звонок»: результат, комментарий, срок, который назвал клиент."""
    raise HTTPException(status_code=501, detail="модуль звонков в разработке (спринт 3)")
