"""Эндпоинты звонков: взятие в работу, событие звонка, история, ответственный.

Авторизации пока нет: оператор передаётся в теле запроса (`operator_id`).
После появления входа его надо брать из токена, а не из тела.
"""
from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from calls import service
from calls.schemas import (
    CallOut,
    CallRequest,
    CallsOut,
    TakeOut,
    TakeRequest,
    WorkOut,
)
from db import SessionLocal

router = APIRouter(tags=["calls"])


def get_db():
    with SessionLocal() as db:
        yield db


def _http_error(exc: service.CallsError) -> NoReturn:
    if isinstance(exc, service.ClientNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, service.AlreadyTaken):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, service.NotOwner):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, service.NoActiveCycle):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    # OperatorNotFound и прочие ошибки входа данных
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def _work_out(client_id: int, cycle, operator_name: str | None) -> WorkOut:
    if cycle is None:
        return WorkOut(client_id=client_id)
    return WorkOut(
        client_id=client_id,
        cycle_id=cycle.id,
        operator_id=cycle.operator_id,
        operator_name=operator_name,
        stage=cycle.stage,
        started_at=cycle.started_at,
    )


@router.post("/clients/{client_id}/take", response_model=TakeOut)
def take_client(client_id: int, payload: TakeRequest,
                db: Session = Depends(get_db)) -> TakeOut:
    """Взять клиента в работу. Повторно — идемпотентно; у коллеги — с takeover."""
    try:
        cycle, takeover = service.take_client(
            db, client_id, payload.operator_id, takeover=payload.takeover,
        )
    except service.CallsError as exc:
        _http_error(exc)
    work = _work_out(client_id, cycle, service.operator_name(db, cycle.operator_id))
    return TakeOut(**work.model_dump(), takeover=takeover)


@router.post("/clients/{client_id}/calls", response_model=CallOut,
             status_code=status.HTTP_201_CREATED)
def add_call(client_id: int, payload: CallRequest,
             db: Session = Depends(get_db)) -> CallOut:
    """Записать звонок: результат, комментарий и обязательный срок клиента."""
    try:
        communication = service.add_call(
            db, client_id, payload.operator_id, payload.promised_date,
            result=payload.result,
            comment=payload.comment,
            contact_type=payload.contact_type,
            called_at=payload.called_at,
        )
    except service.CallsError as exc:
        _http_error(exc)
    return CallOut(
        id=communication.id,
        client_id=communication.client_id,
        cycle_id=communication.cycle_id,
        operator_id=communication.user_id,
        operator_name=service.operator_name(db, communication.user_id) or "",
        contact_type=communication.contact_type,
        result=communication.result,
        comment=communication.comment,
        promised_date=communication.promised_date,
        created_at=communication.created_at,
    )


@router.get("/clients/{client_id}/calls", response_model=CallsOut)
def list_calls(client_id: int, db: Session = Depends(get_db)) -> CallsOut:
    """История коммуникаций по клиенту, новые сверху."""
    try:
        rows = service.list_calls(db, client_id)
    except service.CallsError as exc:
        _http_error(exc)
    return CallsOut(
        client_id=client_id,
        calls=[
            CallOut(
                id=communication.id,
                client_id=communication.client_id,
                cycle_id=communication.cycle_id,
                operator_id=communication.user_id,
                operator_name=name,
                contact_type=communication.contact_type,
                result=communication.result,
                comment=communication.comment,
                promised_date=communication.promised_date,
                created_at=communication.created_at,
            )
            for communication, name in rows
        ],
    )


@router.get("/clients/{client_id}/work", response_model=WorkOut)
def get_work(client_id: int, db: Session = Depends(get_db)) -> WorkOut:
    """Кто ведёт клиента сейчас и на каком этапе."""
    try:
        cycle, operator_name = service.get_work(db, client_id)
    except service.CallsError as exc:
        _http_error(exc)
    return _work_out(client_id, cycle, operator_name)

