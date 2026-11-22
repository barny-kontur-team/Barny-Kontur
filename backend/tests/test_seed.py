import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import seed
from db import Base
from models import AppUser, Client, Communication, DocumentSnapshot, ImportBatch, WorkCycle


@pytest.fixture()
def sessions(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(seed, "SessionLocal", factory)
    monkeypatch.setattr(seed, "init_db", lambda: None)
    try:
        yield factory
    finally:
        engine.dispose()


def test_demo_seed_is_repeatable_and_preserves_existing_changes(sessions):
    assert seed.seed() == (4, 20)
    with sessions.begin() as db:
        client = db.scalar(select(Client).where(Client.kcr_code == "1000001"))
        client.organization_name = "Изменённое тестовое название"
    assert seed.seed() == (0, 0)

    with sessions() as db:
        expected_counts = {Client: 20, AppUser: 4, DocumentSnapshot: 34,
                           ImportBatch: 2, WorkCycle: 13, Communication: 12}
        for model, count in expected_counts.items():
            assert db.scalar(select(func.count()).select_from(model)) == count
        client = db.scalar(select(Client).where(Client.kcr_code == "1000001"))
        assert client.organization_name == "Изменённое тестовое название"
        latest = max(client.snapshots, key=lambda snapshot: snapshot.snapshot_date)
        assert latest.dynamics_code == "DECREASING"


def test_demo_seed_rejects_foreign_client_code(sessions):
    with sessions.begin() as db:
        db.add(Client(kcr_code="1000001", inn="9900000001", organization_name="Другой клиент"))

    with pytest.raises(ValueError, match="1000001"):
        seed.seed()

    with sessions() as db:
        assert db.scalar(select(Client)).organization_name == "Другой клиент"
        assert db.scalar(select(func.count()).select_from(AppUser)) == 0
        assert db.scalar(select(func.count()).select_from(DocumentSnapshot)) == 0
