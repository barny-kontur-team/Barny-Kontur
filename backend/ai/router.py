"""ИИ-помощник: сводка по клиенту и выборка по запросу словами. Только чтение.

Заглушка скелета: спринт 3 (Р-05, H-03/H-05/H-07). Модель — за заменяемым
интерфейсом; для выборки ИИ подбирает условия фильтра, клиентов отбирает код.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["ai"])


@router.post("/clients/{client_id}/summary")
def client_summary(client_id: int) -> None:
    """Сводка по клиенту перед звонком (только чтение)."""
    raise HTTPException(status_code=501, detail="ИИ-модуль в разработке (спринт 3)")


@router.post("/clients/search")
def ai_search() -> None:
    """Выборка по запросу словами: ИИ возвращает условия фильтра, отбор делает код."""
    raise HTTPException(status_code=501, detail="ИИ-модуль в разработке (спринт 3)")
