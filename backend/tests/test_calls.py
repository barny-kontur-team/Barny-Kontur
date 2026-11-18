"""Звонки: взятие в работу, перехват, событие звонка, история.

Тесты не ходят в сеть и не трогают рабочую базу: своя sqlite в памяти.
"""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import models  # noqa: F401 — регистрирует таблицы в Base.metadata
from calls import service
from calls.router import get_db
from db import Base
from main import app
from models import AppUser, Client, WorkCycle


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seed(db):
    client = Client(
        kcr_code="1000001", inn="7701000001", organization_name="ООО «Тест»",
    )
    first = AppUser(
        full_name="Оператор Один", login="op1", password_hash="x", role="OPERATOR",
    )
    second = AppUser(
        full_name="Оператор Два", login="op2", password_hash="x", role="OPERATOR",
    )
    db.add_all([client, first, second])
    db.commit()
    return {"client": client.id, "op1": first.id, "op2": second.id}


def test_take_sets_owner_and_first_call_stage(db, seed):
    cycle, takeover = service.take_client(db, seed["client"], seed["op1"])
    assert cycle.operator_id == seed["op1"]
    assert cycle.stage == service.STAGE_FIRST_CALL
    assert takeover is False


def test_take_is_idempotent_for_same_operator(db, seed):
    first, _ = service.take_client(db, seed["client"], seed["op1"])
    second, takeover = service.take_client(db, seed["client"], seed["op1"])
    assert first.id == second.id
    assert takeover is False


def test_take_by_other_operator_requires_takeover(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    with pytest.raises(service.AlreadyTaken) as info:
        service.take_client(db, seed["client"], seed["op2"])
    assert info.value.operator_name == "Оператор Один"


def test_takeover_changes_operator(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    cycle, takeover = service.take_client(
        db, seed["client"], seed["op2"], takeover=True,
    )
    assert takeover is True
    assert cycle.operator_id == seed["op2"]


def test_only_one_active_cycle_per_client(db):
    """WC-01: уникальный индекс не даёт открыть два активных цикла."""
    client = Client(kcr_code="1000002", inn="7701000002", organization_name="ООО «Тест-2»")
    db.add(client)
    db.commit()
    db.add_all([
        WorkCycle(client_id=client.id, stage="Первый звонок", started_at=datetime.now()),
        WorkCycle(client_id=client.id, stage="Первый звонок", started_at=datetime.now()),
    ])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_call_requires_active_cycle(db, seed):
    with pytest.raises(service.NoActiveCycle):
        service.add_call(db, seed["client"], seed["op1"], date(2026, 6, 1))


def test_call_only_by_owner(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    with pytest.raises(service.NotOwner):
        service.add_call(db, seed["client"], seed["op2"], date(2026, 6, 1))


def test_call_saves_promised_date_and_history(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    communication = service.add_call(
        db, seed["client"], seed["op1"], date(2026, 6, 1),
        result="Дозвонились", comment="Обещал привезти",
    )
    assert communication.promised_date == date(2026, 6, 1)

    history = service.list_calls(db, seed["client"])
    assert len(history) == 1
    assert history[0][0].id == communication.id
    assert history[0][1] == "Оператор Один"


def test_history_newest_first(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    older = service.add_call(
        db, seed["client"], seed["op1"], date(2026, 6, 1),
        called_at=datetime(2026, 5, 1, 10, 0),
    )
    newer = service.add_call(
        db, seed["client"], seed["op1"], date(2026, 7, 1),
        called_at=datetime(2026, 6, 1, 10, 0),
    )
    ids = [communication.id for communication, _ in service.list_calls(db, seed["client"])]
    assert ids == [newer.id, older.id]


def test_backdated_call_keeps_called_at(db, seed):
    service.take_client(db, seed["client"], seed["op1"])
    communication = service.add_call(
        db, seed["client"], seed["op1"], date(2026, 6, 1),
        called_at=datetime(2026, 4, 10, 9, 30),
    )
    assert communication.created_at == datetime(2026, 4, 10, 9, 30)


def test_unknown_client_and_operator(db, seed):
    with pytest.raises(service.ClientNotFound):
        service.take_client(db, 999_999, seed["op1"])
    with pytest.raises(service.OperatorNotFound):
        service.take_client(db, seed["client"], 999_999)


# --- HTTP-слой -------------------------------------------------------------

@pytest.fixture()
def http(db):
    def override():
        yield db

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_http_take_call_and_history(http, seed):
    url = f"/api/clients/{seed['client']}"

    response = http.post(f"{url}/take", json={"operator_id": seed["op1"]})
    assert response.status_code == 200
    assert response.json()["stage"] == "Первый звонок"

    response = http.post(f"{url}/calls", json={
        "operator_id": seed["op1"],
        "promised_date": "2026-06-01",
        "result": "Дозвонились",
    })
    assert response.status_code == 201

    response = http.get(f"{url}/calls")
    assert response.status_code == 200
    assert response.json()["calls"][0]["promised_date"] == "2026-06-01"

    response = http.get(f"{url}/work")
    assert response.status_code == 200
    assert response.json()["operator_id"] == seed["op1"]


def test_http_take_conflict_and_takeover(http, seed):
    url = f"/api/clients/{seed['client']}"
    assert http.post(f"{url}/take", json={"operator_id": seed["op1"]}).status_code == 200

    response = http.post(f"{url}/take", json={"operator_id": seed["op2"]})
    assert response.status_code == 409

    response = http.post(f"{url}/take", json={
        "operator_id": seed["op2"], "takeover": True,
    })
    assert response.status_code == 200
    assert response.json()["takeover"] is True


def test_http_call_requires_promised_date(http, seed):
    url = f"/api/clients/{seed['client']}"
    assert http.post(f"{url}/take", json={"operator_id": seed["op1"]}).status_code == 200
    response = http.post(f"{url}/calls", json={"operator_id": seed["op1"]})
    assert response.status_code == 422


def test_http_call_without_take_returns_409(http, seed):
    response = http.post(f"/api/clients/{seed['client']}/calls", json={
        "operator_id": seed["op1"], "promised_date": "2026-06-01",
    })
    assert response.status_code == 409
