"""Загрузка тестового набора H-02 в модель, понятную модулю ai.

Разбор Excel — здесь, в scripts, а не в модуле ai: ai не должен знать,
откуда пришли цифры (правило 3 AGENTS.md). Правила динамики берём готовые
из backend/dynamics/features.py — второй раз их не пишем (правило 5).

Данные: data/test/h02/01_Корректные_импорты (обезличенный набор DS-02).
Звонки и этапы: scripts/h03/fixture.json (фикстура из протокола H-03, раздел 1.2).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import openpyxl

from ai.schemas import ClientView, SnapshotView

H02_DIR = Path(__file__).resolve().parents[2] / "data" / "test" / "h02"
DATA_DIR = H02_DIR / "01_Корректные_импорты"
FIXTURE = Path(__file__).resolve().parent / "fixture.json"
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

# Правила динамики — один источник: backend/dynamics/features.py (после
# переноса H-02 в сервис). Скрипт h02 оставлен как история проверки.
sys.path.insert(0, str(BACKEND_DIR))
from dynamics import features as h02  # noqa: E402

SLICE_RE = re.compile(r"^(?P<id>S\d+)_(?P<period>.+)_(?P<date>\d{4}-\d{2}-\d{2})\.xlsx$")

SHEET = "Данные"


def _rows(path: Path) -> list[tuple]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[SHEET] if SHEET in workbook.sheetnames else workbook.worksheets[0]
        iterator = sheet.iter_rows(values_only=True)
        next(iterator, None)  # заголовок
        return [row for row in iterator if any(value is not None for value in row)]
    finally:
        workbook.close()


def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip())


def _period_from_name(name: str) -> str:
    # I_кв_2026 -> «I кв. 2026»: формат нужен features.previous_quarter
    raw = name.replace("_", " ").strip()
    match = re.match(r"^(I|II|III|IV)\s+кв\s+(\d{4})$", raw)
    if not match:
        raise ValueError(f"не разобрать период из имени файла: {name}")
    return f"{match.group(1)} кв. {match.group(2)}"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_raw() -> tuple[list[h02.RawSlice], dict[str, h02.Client], dict]:
    """Читает клиентов, срезы и фикстуру звонков в структуры features.py."""
    fixture = load_fixture()
    stages: dict[str, str] = fixture.get("stages", {})
    calls: dict[str, dict] = fixture.get("calls", {})

    clients: dict[str, h02.Client] = {}
    client_rows = _rows(DATA_DIR / "00_Клиенты.xlsx")
    for code, inn, kpp, name, client_type, connected, do_not_call in client_rows:
        code = str(code).strip()
        clients[code] = h02.Client(
            code=code,
            connect_date=_as_date(connected),
            do_not_call=str(do_not_call or "").strip().lower() in ("да", "yes", "true", "1"),
            stage=stages.get(code),
        )

    slices: list[h02.RawSlice] = []
    for path in sorted(DATA_DIR.glob("S*.xlsx")):
        match = SLICE_RE.match(path.name)
        if not match:
            raise ValueError(f"не разобрать имя среза: {path.name}")
        slice_id = match.group("id")
        period = _period_from_name(match.group("period"))
        slice_date = date.fromisoformat(match.group("date"))
        for code, total, missing in _rows(path):
            slices.append(h02.RawSlice(
                slice_id=slice_id,
                period=period,
                slice_date=slice_date,
                code=str(code).strip(),
                total=int(total) if total is not None else None,
                not_transferred=int(missing or 0),
            ))

    unknown = {s.code for s in slices} - set(clients)
    if unknown:
        raise ValueError(f"в срезах есть неизвестные коды КЦР: {sorted(unknown)}")

    slices.sort(key=lambda s: (s.slice_date, s.slice_id, s.code))
    return slices, clients, calls


def load_clients() -> list[ClientView]:
    """Готовый список клиентов с историей, признаками и пулом обзвона."""
    slices, clients, calls = load_raw()
    calculator = h02.FeatureCalculator(clients)
    rows = calculator.process(slices)

    by_code: dict[str, list[SnapshotView]] = {}
    for row in rows:
        client = clients[row.code]
        by_code.setdefault(row.code, []).append(SnapshotView(
            slice_id=row.slice_id,
            period=row.period,
            date=row.slice_date,
            missing=row.not_transferred,
            total=row.total_ref,
            change=row.change,
            is_novice=row.is_novice,
            is_chronic=row.is_chronic,
            category=row.category,
            in_pool=calculator.in_call_pool(row, client),
        ))

    result: list[ClientView] = []
    for code, client in sorted(clients.items()):
        call = calls.get(code, {})
        result.append(ClientView(
            code=code,
            name=client_name(code),
            inn=client_inn(code),
            kpp=client_kpp(code),
            client_type=client_type(code),
            connected_at=client.connect_date,
            do_not_call=client.do_not_call,
            stage=client.stage,
            last_call_date=_as_date(call.get("last_call")),
            promised_date=_as_date(call.get("promised")),
            snapshots=sorted(by_code.get(code, []), key=lambda s: s.date),
        ))
    return result


# --- справочник реквизитов (читается один раз) -----------------------------

_CLIENT_INFO: dict[str, dict] | None = None


def _load_info() -> dict[str, dict]:
    global _CLIENT_INFO
    if _CLIENT_INFO is None:
        _CLIENT_INFO = {}
        for code, inn, kpp, name, client_type, _, _ in _rows(DATA_DIR / "00_Клиенты.xlsx"):
            _CLIENT_INFO[str(code).strip()] = {
                "inn": str(inn or "").strip(),
                "kpp": str(kpp).strip() if kpp else None,
                "name": str(name or "").strip(),
                "client_type": str(client_type).strip() if client_type else None,
            }
    return _CLIENT_INFO


def client_name(code: str) -> str:
    return _load_info().get(code, {}).get("name", "")


def client_inn(code: str) -> str:
    return _load_info().get(code, {}).get("inn", "")


def client_kpp(code: str) -> str | None:
    return _load_info().get(code, {}).get("kpp")


def client_type(code: str) -> str | None:
    return _load_info().get(code, {}).get("client_type")
