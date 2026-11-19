"""Динамика: история клиента и список клиентов для экранов.

Модель Б хранится по срезам; здесь она отдаётся наружу в готовом виде.
Список клиентов нужен фронтенду: без него экран не знает ID базы.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Client, DocumentSnapshot

from .service import present

router = APIRouter(tags=["dynamics"])


def get_db():
    with SessionLocal() as db:
        yield db


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _total_ref(snapshot: DocumentSnapshot, previous_total: int | None) -> int | None:
    """Опорный total периода: в повторных срезах колонка пустая.

    Берём значение из первого среза периода; если его нет — восстанавливаем
    из процента, иначе тянем последнее известное.
    """
    if snapshot.total_documents is not None:
        return snapshot.total_documents
    percent = snapshot.missing_percent
    if percent and snapshot.missing_documents:
        return round(snapshot.missing_documents / (percent / 100))
    return previous_total


def _in_pool(client: Client, snapshot: DocumentSnapshot) -> bool:
    """Пул обзвона: есть непереданные, известен total, доля ≥ 5% или новичок."""
    if client.is_do_not_work or snapshot.missing_documents <= 0:
        return False
    if snapshot.missing_percent is None:
        return False
    share_ok = snapshot.missing_percent >= 5
    novice_ok = bool(snapshot.is_novice)
    return share_ok or novice_ok


def _history(client: Client, rows: list[DocumentSnapshot]) -> list[dict]:
    history: list[dict] = []
    previous_total: int | None = None
    for snapshot in rows:
        total = _total_ref(snapshot, previous_total)
        previous_total = total
        item = present(snapshot)
        history.append({
            "snapshot_id": item["snapshot_id"],
            "date": item["snapshot_date"],
            "period": item["reporting_period"],
            "missing": item["missing_documents"],
            "total": total,
            "percent": item["missing_percent"],
            "dynamics_code": item["dynamics_code"],
            "dynamics_name": item["dynamics_name"],
            "category": item["category"],
            "is_novice": item["is_novice"],
            "is_chronic": item["is_chronic"],
            "in_pool": _in_pool(client, snapshot),
        })
    return history


@router.get("/clients")
def list_clients(db: Session = Depends(get_db)) -> dict:
    """Список клиентов с историей срезов. ID здесь — ID базы, не код КЦР."""
    clients = db.scalars(select(Client).order_by(Client.kcr_code)).all()
    rows = db.scalars(
        select(DocumentSnapshot).order_by(
            DocumentSnapshot.client_id, DocumentSnapshot.snapshot_date, DocumentSnapshot.id,
        )
    ).all()
    by_client: dict[int, list[DocumentSnapshot]] = {}
    for snapshot in rows:
        by_client.setdefault(snapshot.client_id, []).append(snapshot)

    result = []
    for client in clients:
        history = _history(client, by_client.get(client.id, []))
        result.append({
            "id": client.id,
            "kcr_code": client.kcr_code,
            "inn": client.inn,
            "kpp": client.kpp,
            "name": client.organization_name,
            "client_type": client.client_type,
            "connected_at": _iso(client.connection_date),
            "do_not_call": bool(client.is_do_not_work),
            "first_appearance_date": _iso(client.first_appearance_date),
            "history": history,
            "last": history[-1] if history else None,
            "previous": history[-2] if len(history) > 1 else None,
        })
    return {"clients": result}


@router.get("/clients/{client_id}/dynamics")
def client_dynamics(client_id: int, db: Session = Depends(get_db)) -> dict:
    client = db.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    rows = db.scalars(
        select(DocumentSnapshot)
        .where(DocumentSnapshot.client_id == client_id)
        .order_by(DocumentSnapshot.snapshot_date, DocumentSnapshot.id)
    ).all()
    return {
        "client_id": client.id,
        "kcr_code": client.kcr_code,
        "first_appearance_date": _iso(client.first_appearance_date),
        "history": [present(snapshot) for snapshot in rows],
    }
