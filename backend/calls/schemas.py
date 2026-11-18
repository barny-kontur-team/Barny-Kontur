"""Схемы запросов и ответов модуля звонков."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class TakeRequest(BaseModel):
    """Кто берёт клиента. `takeover=True` — забрать у коллеги."""

    operator_id: int = Field(gt=0)
    takeover: bool = False


class CallRequest(BaseModel):
    """Событие звонка. Срок клиента (`promised_date`) обязателен."""

    operator_id: int = Field(gt=0)
    promised_date: date
    result: str | None = Field(default=None, max_length=100)
    comment: str | None = None
    contact_type: str = "звонок"
    called_at: datetime | None = None


class WorkOut(BaseModel):
    client_id: int
    cycle_id: int | None = None
    operator_id: int | None = None
    operator_name: str | None = None
    stage: str | None = None
    started_at: datetime | None = None


class TakeOut(WorkOut):
    takeover: bool = False


class CallOut(BaseModel):
    id: int
    client_id: int
    cycle_id: int | None = None
    operator_id: int
    operator_name: str
    contact_type: str
    result: str | None = None
    comment: str | None = None
    promised_date: date | None = None
    created_at: datetime


class CallsOut(BaseModel):
    client_id: int
    calls: list[CallOut]
