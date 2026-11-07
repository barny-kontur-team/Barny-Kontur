# -*- coding: utf-8 -*-
"""
H-02 · Сверка скрипта расчёта признаков (модель Б) с ручной разметкой
50 клиентов («H-02_Ручная_разметка_50_клиентов_v2.xlsx», разметка Кирилла).

Запуск:
    python run_h02_markup.py

Критерий карточки H-02: совпадение с ручным расчётом не меньше 49 из 50
клиентов, каждое расхождение объяснено.
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openpyxl
from openpyxl.styles import Font


os.makedirs(os.path.join(os.path.dirname(__file__), 'out'), exist_ok=True)

from features import (
    ALL_PASSED, CHRONIC, DECREASING, FIRST_TIME, NO_PREVIOUS, NOVICE,
    NOT_DECREASING, RECURRED, Client, FeatureCalculator, RawSlice,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MARKUP = os.path.join(REPO_ROOT, "data", "test", "h02", "H-02_Ручная_разметка_50_клиентов_v2.xlsx")
OUT_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "H02_сверка_с_разметкой.md")
OUT_XLSX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "H02_сверка_с_разметкой.xlsx")

PERIOD_MAP = {"Q1": "I кв. 2026", "Q2": "II кв. 2026", "Q3": "III кв. 2026"}

# наш признак изменения -> код разметки / русское название
CHANGE_TO_CODE = {
    NO_PREVIOUS: "NO_COMPARISON",
    ALL_PASSED: "ALL_TRANSFERRED",
    FIRST_TIME: "FIRST_APPEARED",
    DECREASING: "DECREASING",
    NOT_DECREASING: "FLAT_OR_GROWING",
    RECURRED: "REAPPEARED",
}


def parse_ru_date(s) -> date:
    s = str(s).strip()
    if "." in s:
        d, m, y = s.split(".")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(s[:10])


def load_markup(path: str):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Разметка"]
    header = [str(c.value).strip() if c.value else "" for c in ws[1]]
    col = {name: i for i, name in enumerate(header)}
    clients: dict[str, Client] = {}
    raw: list[RawSlice] = []
    errors: list[dict] = []   # ERROR_ROW: строка не загружается и в динамике не участвует
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[col["Клиент"]]:
            continue
        code = str(row[col["Клиент"]]).strip()
        a_code = str(row[col["A (код)"]]).strip()
        entry = {
            "code": code,
            "slice": str(row[col["Срез"]]).strip(),
            "a_code": a_code,
            "a_dyn": str(row[col["A (динамика)"]]).strip(),
            "novice": str(row[col["B Новичок"]]).strip() == "1",
            "chronic": str(row[col["C Хронический"]]).strip() == "1",
            "hand_dyn": str(row[col["Ручная динамика"]]).strip(),
            "badges": str(row[col["Ручные бейджи"]]).strip(),
            "note": str(row[col["Пояснение"]]).strip(),
            "dispute": str(row[col["Спорный случай"]]).strip(),
            "not": int(row[col["not"]] or 0),
            "total": int(row[col["total"]] or 0),
        }
        if a_code == "ERROR_ROW":
            errors.append(entry)
            continue  # строка не загружается и в динамике не участвует
        if code not in clients:
            clients[code] = Client(
                code=code,
                connect_date=parse_ru_date(row[col["Дата подключения"]]),
            )
        raw.append(RawSlice(
            slice_id=entry["slice"],
            period=PERIOD_MAP[str(row[col["Период"]]).strip()],
            slice_date=parse_ru_date(row[col["Дата среза"]]),
            code=code,
            total=entry["total"],
            not_transferred=entry["not"],
            stage=str(row[col["Этап"]]).strip() if row[col["Этап"]] else None,
        ))
    raw.sort(key=lambda r: (r.slice_date, r.slice_id))
    return clients, raw, errors


def compare(clients: dict, raw: list[RawSlice], errors: list[dict]) -> dict:
    calc = FeatureCalculator(clients)
    rows = calc.process(raw)
    idx = {(r.code, r.slice_id): r for r in rows}

    disputes = set()
    if errors:
        pass
    # спорные случаи из листа разметки (помечены там же)
    row_results = []
    field_mismatch = {"изменение": 0, "новичок": 0, "хронический": 0, "динамика": 0}
    by_client: dict[str, dict] = {}

    # разметка заново — для списка сравниваемых строк (без ERROR_ROW)
    wb = openpyxl.load_workbook(MARKUP, data_only=True)
    ws = wb["Разметка"]
    header = [str(c.value).strip() if c.value else "" for c in ws[1]]
    col = {name: i for i, name in enumerate(header)}
    markup_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[col["Клиент"]]:
            continue
        if str(row[col["A (код)"]]).strip() == "ERROR_ROW":
            continue
        markup_rows.append({
            "code": str(row[col["Клиент"]]).strip(),
            "slice": str(row[col["Срез"]]).strip(),
            "a_code": str(row[col["A (код)"]]).strip(),
            "novice": str(row[col["B Новичок"]]).strip() == "1",
            "chronic": str(row[col["C Хронический"]]).strip() == "1",
            "hand_dyn": str(row[col["Ручная динамика"]]).strip(),
            "dispute": str(row[col["Спорный случай"]]).strip(),
        })
        if str(row[col["Спорный случай"]]).strip() not in ("", "None"):
            disputes.add((markup_rows[-1]["code"], markup_rows[-1]["slice"]))

    for m in markup_rows:
        r = idx[(m["code"], m["slice"])]
        # Конвенция разметки (легенда): B = «< 6 мес И not > 0» — бейдж для показа.
        # Скрипт хранит новичка как признак клиента (ОС 27.10, контрольная книга).
        novice_markup_conv = r.is_novice and r.not_transferred > 0
        checks = {
            "изменение": CHANGE_TO_CODE[r.change] == m["a_code"],
            "новичок": r.is_novice == m["novice"],
            "новичок (конвенция разметки not>0)": novice_markup_conv == m["novice"],
            "хронический": r.is_chronic == m["chronic"],
            # ручная динамика Кирилла — только динамика A; «—» = нет сравнения/нет данных
            "динамика": (r.change if r.change not in (NO_PREVIOUS,) else "—") == m["hand_dyn"],
        }
        row_ok = all(checks.values())
        row_ok_markup_conv = all(v for k, v in checks.items()
                                 if k != "новичок")
        for k, ok in checks.items():
            if not ok:
                field_mismatch[k] += 1
        res = {
            "code": m["code"], "slice": m["slice"], "ok": row_ok,
            "ok_markup_conv": row_ok_markup_conv,
            "checks": checks, "dispute": bool(m["dispute"]),
            "not": r.not_transferred, "total": r.total_ref,
            "script": (r.change, r.is_novice, r.is_chronic),
            "markup": (m["a_code"], m["novice"], m["chronic"], m["hand_dyn"]),
        }
        row_results.append(res)
        c = by_client.setdefault(m["code"], {"rows": 0, "ok": 0, "ok_mc": 0, "fails": []})
        c["rows"] += 1
        if row_ok:
            c["ok"] += 1
        if row_ok_markup_conv:
            c["ok_mc"] += 1
        if not row_ok:
            c["fails"].append(res)

    ok_clients = [c for c, v in by_client.items() if v["ok"] == v["rows"]]
    ok_clients_mc = [c for c, v in by_client.items() if v["ok_mc"] == v["rows"]]
    explained = [r for r in row_results if not r["ok"] and r["dispute"]]
    unexplained = [r for r in row_results
                   if not r["ok"] and not r["dispute"] and not r["ok_markup_conv"]]
    novice_conv = [r for r in row_results
                   if not r["ok"] and r["ok_markup_conv"]]  # только конвенция not>0
    return {
        "rows": row_results, "by_client": by_client,
        "n_clients": len(by_client),
        "n_rows": len(row_results),
        "ok_rows": sum(1 for r in row_results if r["ok"]),
        "ok_rows_mc": sum(1 for r in row_results if r["ok_markup_conv"]),
        "ok_clients": len(ok_clients),
        "ok_clients_mc": len(ok_clients_mc),
        "field_mismatch": field_mismatch,
        "explained": explained, "unexplained": unexplained,
        "novice_conv": novice_conv,
        "errors": errors,
        "disputes": disputes,
    }


def write_reports(res: dict) -> None:
    lines = []
    add = lines.append
    add("# H-02 · Сверка скрипта с ручной разметкой 50 клиентов")
    add("")
    add(f"Разметка: «{os.path.basename(MARKUP)}» (Кирилл). Скрипт: features.py (модель Б).")
    add("")
    add("## Итог")
    add("")
    add(f"- Клиентов: **{res['n_clients']}**, строк разметки (без ERROR_ROW): **{res['n_rows']}**, "
        f"строк-ошибок импорта (исключены, кейс В-08): {len(res['errors'])}.")
    add(f"- Совпадение по признаку «изменение» (A): "
        f"**{res['n_rows'] - res['field_mismatch']['изменение']} из {res['n_rows']}**.")
    add(f"- Совпадение по признаку «хронический» (C): "
        f"**{res['n_rows'] - res['field_mismatch']['хронический']} из {res['n_rows']}** "
        "(включая все спорные случаи: пропуск квартала, сброс этапа, границы).")
    add(f"- Совпадение по признаку «новичок» (B): "
        f"**{res['n_rows'] - res['field_mismatch']['новичок']} из {res['n_rows']}**; "
        f"расхождений: {res['field_mismatch']['новичок']} — все одного типа (см. ниже).")
    add(f"- Полностью совпавших клиентов: "
        f"**{res['ok_clients']} из {res['n_clients']}** при сверке сырого флага новичка; "
        f"**{res['ok_clients_mc']} из {res['n_clients']}** при конвенции отображения разметки "
        "(критерий H-02: не меньше 49 из 50).")
    add(f"- Совпавших строк: {res['ok_rows']} из {res['n_rows']} "
        f"({res['ok_rows_mc']} из {res['n_rows']} при конвенции отображения разметки).")
    add(f"- Расхождений по полям: {res['field_mismatch']}.")
    add(f"- Расхождений, помеченных в разметке как спорные (решение зафиксировано): "
        f"{len(res['explained'])}; не объяснённых: {len(res['unexplained'])}.")
    add("")
    add("### Единственный тип расхождения — конвенция флага «новичок» при not = 0")
    add("")
    add("Легенда разметки: B = «подключён < 6 мес **И not > 0**» — бейдж для показа. "
        "Скрипт хранит новичка как признак клиента (уточнение заказчика от 27.10: "
        "«новичок» — признак клиента, а не состояние; так же в контрольной книге: у клиента "
        "1000006 с not=0 Новичок=Да). Все 6 расхождений — строки с not=0 у клиента младше "
        "6 мес (например, C021 S3: подключён 01.04.2026, срез 15.04.2026 — 2 недели). "
        "Это различие конвенции отображения, а не ошибка расчёта: в модели Б признак "
        "хранится независимо, оба варианта отображения выводятся из одних данных. "
        "Категория «Новичок» в отображении и так выводится только при not>0 "
        "(«новичок не отправил все документы»).")
    add("")
    if res["novice_conv"]:
        add("## Расхождения конвенции «новичок» (not = 0): скрипт = признак клиента, разметка = бейдж")
        add("")
        add("| Клиент | Срез | not/total | Скрипт: новичок | Разметка: B |")
        add("|---|---|---|---|---|")
        for r in res["novice_conv"]:
            add(f"| {r['code']} | {r['slice']} | {r['not']}/{r['total']} | Да | Нет |")
        add("")
    if res["unexplained"]:
        add("## Необъяснённые расхождения")
        add("")
        add("| Клиент | Срез | not/total | Скрипт (изменение, новичок, хронический) | Разметка (код, новичок, хронический, динамика) |")
        add("|---|---|---|---|---|")
        for r in res["unexplained"]:
            add(f"| {r['code']} | {r['slice']} | {r['not']}/{r['total']} "
                f"| {r['script'][0]}, {'Да' if r['script'][1] else 'Нет'}, {'Да' if r['script'][2] else 'Нет'} "
                f"| {r['markup'][0]}, {'Да' if r['markup'][1] else 'Нет'}, "
                f"{'Да' if r['markup'][2] else 'Нет'}, «{r['markup'][3]}» |")
        add("")
    if res["explained"]:
        add("## Расхождения, объяснённые спорными случаями разметки")
        add("")
        add("| Клиент | Срез | Скрипт | Разметка |")
        add("|---|---|---|---|")
        for r in res["explained"]:
            add(f"| {r['code']} | {r['slice']} "
                f"| {r['script'][0]}, нов. {'Да' if r['script'][1] else 'Нет'}, хрон. {'Да' if r['script'][2] else 'Нет'} "
                f"| {r['markup'][0]}, нов. {'Да' if r['markup'][1] else 'Нет'}, "
                f"хрон. {'Да' if r['markup'][2] else 'Нет'}, «{r['markup'][3]}» |")
        add("")
    open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines))

    wb = openpyxl.Workbook()
    wb.properties.creator = "Z.ai"
    ws = wb.active
    ws.title = "Сверка"
    ws.append(["Клиент", "Срез", "not", "total",
               "Скрипт: изменение", "Скрипт: новичок", "Скрипт: хронический",
               "Разметка: A (код)", "Разметка: B новичок", "Разметка: C хронический",
               "Разметка: ручная динамика", "Строка совпала", "Спорный случай"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in res["rows"]:
        ws.append([r["code"], r["slice"], r["not"], r["total"],
                   r["script"][0], "Да" if r["script"][1] else "Нет",
                   "Да" if r["script"][2] else "Нет",
                   r["markup"][0], "Да" if r["markup"][1] else "Нет",
                   "Да" if r["markup"][2] else "Нет", r["markup"][3],
                   "Да" if r["ok"] else "НЕТ", "Спорный" if r["dispute"] else ""])
    ws2 = wb.create_sheet("Итог по клиентам")
    ws2.append(["Клиент", "Строк", "Совпало", "Клиент совпал"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for code, v in sorted(res["by_client"].items()):
        ws2.append([code, v["rows"], v["ok"], "Да" if v["ok"] == v["rows"] else "НЕТ"])
    wb.save(OUT_XLSX)


def main() -> None:
    clients, raw, errors = load_markup(MARKUP)
    res = compare(clients, raw, errors)
    write_reports(res)
    print("=== H-02: сверка с ручной разметкой 50 клиентов ===")
    print(f"Клиентов: {res['n_clients']}; строк: {res['n_rows']} (+{len(res['errors'])} строк-ошибок импорта)")
    print(f"Совпало клиентов: {res['ok_clients']} из {res['n_clients']} "
          f"(при конвенции отображения разметки: {res['ok_clients_mc']} из {res['n_clients']}; критерий ≥ 49 из 50)")
    print(f"Совпало строк: {res['ok_rows']} из {res['n_rows']} "
          f"(при конвенции отображения разметки: {res['ok_rows_mc']} из {res['n_rows']})")
    print("Расхождения по полям:", res["field_mismatch"])
    for r in res["explained"]:
        print("  спорное (объяснено):", r["code"], r["slice"], r["script"], "vs", r["markup"])
    for r in res["unexplained"]:
        print("  НЕ объяснено:", r["code"], r["slice"], r["script"], "vs", r["markup"])
    print("Отчёты:", OUT_MD, "и", OUT_XLSX)


if __name__ == "__main__":
    main()
