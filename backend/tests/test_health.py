"""Тесты скелета: /health живёт, модули-заглушки отвечают 501, таблицы создаются."""
from fastapi.testclient import TestClient

from main import app

STUB_POST_ENDPOINTS = (
    "/api/imports/clients",
    "/api/imports/snapshots",
    "/api/clients/1/take",
    "/api/clients/1/calls",
    "/api/clients/1/summary",
    "/api/clients/search",
)


def test_health_ok():
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] in ("ok", "down")  # без Docker база может быть не поднята


def test_stub_modules_return_501():
    with TestClient(app) as client:
        for path in STUB_POST_ENDPOINTS:
            resp = client.post(path)
            assert resp.status_code == 501, path


def test_tables_created():
    """Запуск приложения создаёт схему из models.py (9 таблиц)."""
    from db import Base, engine
    with TestClient(app):
        pass
    tables = set(Base.metadata.tables)
    expected = {"client", "document_snapshot", "app_user", "work_cycle",
                "communication", "task", "claim", "sanction", "import_batch"}
    assert expected <= tables
    engine.dispose()
