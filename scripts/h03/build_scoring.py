"""Собирает таблицу для ручной разметки блока А (15 сводок × 3 модели).

На вход — результаты прогона в scripts/h03/out/<модель>/answers.jsonl.
На выход — scripts/h03/out/h03_scoring.xlsx: по листу на модель, чек-лист
из протокола 2.2, формулы для подсчёта полных ответов и факт-ошибок.

Запуск:
  python scripts/h03/build_scoring.py
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
QUESTIONS = HERE / "questions.json"
SCORING = HERE / "scoring.json"

HEADERS = [
    "№", "ID", "Клиент", "Эталон", "Ответ модели", "Последний срез (сверка)",
    "Звонки", "Обещание", "Динамика", "Итог", "Полный", "Факт-ошибок", "Комментарий",
]
WIDTHS = [5, 8, 24, 62, 62, 34, 9, 10, 11, 8, 9, 12, 34]

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
RED_FILL = PatternFill("solid", fgColor="F8CBAD")
GREEN_FILL = PatternFill("solid", fgColor="C6EFCE")
GREY_FILL = PatternFill("solid", fgColor="F2F2F2")


def load_questions() -> dict:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


def load_scoring() -> dict:
    if not SCORING.exists():
        return {}
    return json.loads(SCORING.read_text(encoding="utf-8"))


def yn(value) -> str:
    if value is True:
        return "Да"
    if value is False:
        return "Нет"
    return ""


def load_records(model_dir: Path) -> list[dict]:
    path = model_dir / "answers.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def last_slice_text(record: dict) -> str:
    last = record.get("last_slice")
    if not last:
        return "—"
    share = "—" if last["share"] is None else f"{last['share']}%"
    pool = "в пуле" if last["in_pool"] else "вне пула"
    return f"{last['slice_id']}: {last['missing']}/{last['total']}, {share}, «{last['category']}», {pool}"


def style_header(ws) -> None:
    for column, (title, width) in enumerate(zip(HEADERS, WIDTHS), start=1):
        cell = ws.cell(row=1, column=column, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(column)].width = width
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = "D2"


def build_model_sheet(wb: Workbook, title: str, records: list[dict], questions: dict,
                      scoring: dict) -> None:
    ws = wb.create_sheet(title[:31])
    style_header(ws)
    etalons = {item["id"]: item for item in questions["blocks"]["A"]}

    for row, record in enumerate(records, start=2):
        item = etalons.get(record["id"], {})
        marks = scoring.get(record["id"], {})
        values = [
            row - 1, record["id"], item.get("org", ""), item.get("etalon", ""),
            record.get("answer", ""), last_slice_text(record),
            yn(marks.get("calls")), yn(marks.get("promise")),
            yn(marks.get("dynamics")), yn(marks.get("total")), None,
            marks.get("errors"), marks.get("comment", ""),
        ]
        for column, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=column, value=value)
            cell.border = BORDER
            cell.alignment = CENTER if column in (1, 2, 7, 8, 9, 10, 11, 12) else WRAP
        ws.cell(row=row, column=11,
                value=f'=IF(COUNTIF(G{row}:J{row},"Да")+COUNTIF(G{row}:J{row},"Нет")<4,"",'
                      f'IF(COUNTIF(G{row}:J{row},"Да")=4,"Да","Нет"))')
        ws.cell(row=row, column=11).alignment = CENTER
        ws.cell(row=row, column=11).border = BORDER

        # высота строки под длинный текст
        length = max(len(item.get("etalon", "")), len(record.get("answer", "")))
        ws.row_dimensions[row].height = min(300, max(60, length / 55 * 15))

    last_row = len(records) + 1
    validation = DataValidation(type="list", formula1='"Да,Нет"', allow_blank=True,
                                showDropDown=False)
    ws.add_data_validation(validation)
    validation.add(f"G2:J{last_row}")

    ws.conditional_formatting.add(
        f"K2:K{last_row}",
        CellIsRule(operator="equal", formula=['"Нет"'], fill=RED_FILL),
    )
    ws.conditional_formatting.add(
        f"K2:K{last_row}",
        CellIsRule(operator="equal", formula=['"Да"'], fill=GREEN_FILL),
    )
    ws.conditional_formatting.add(
        f"L2:L{last_row}",
        CellIsRule(operator="greaterThan", formula=["0"], fill=RED_FILL),
    )
    ws.auto_filter.ref = f"A1:M{last_row}"


def build_summary(wb: Workbook, sheets: dict[str, tuple[str, list[dict]]]) -> None:
    ws = wb.create_sheet("Сводка", 0)
    ws.column_dimensions["A"].width = 26
    for column in "BCDEF":
        ws.column_dimensions[column].width = 16

    ws["A1"] = "H-03: сводка по моделям"
    ws["A1"].font = Font(bold=True, size=14)

    headers = ["Модель", "А: полных", "А: факт-ошибок", "Б: совпало", "В: «нет данных»"]
    for column, title in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=column, value=title)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER

    for row, (display, (sheet, records)) in enumerate(sheets.items(), start=4):
        b = [r for r in records if r["block"] == "B"]
        c = [r for r in records if r["block"] == "C"]
        b_ok = sum(1 for r in b if r["auto"] == "ok")
        c_ok = sum(1 for r in c if r["auto"] == "ok")
        ws.cell(row=row, column=1, value=display).border = BORDER
        ws.cell(row=row, column=2, value=f'=COUNTIF(\'{sheet}\'!K:K,"Да")').border = BORDER
        ws.cell(row=row, column=3, value=f"=SUM('{sheet}'!L:L)").border = BORDER
        ws.cell(row=row, column=4, value=f"{b_ok}/{len(b)}").border = BORDER
        ws.cell(row=row, column=5, value=f"{c_ok}/{len(c)}").border = BORDER

    ws["A10"] = "Критерий H-03"
    ws["A10"].font = Font(bold=True)
    ws["A11"] = "Блок А: не меньше 13 из 15 полных, 0 факт-ошибок"
    ws["A12"] = "Блок Б: 12 из 12"
    ws["A13"] = "Блок В: 3 из 3"
    ws["A15"] = "Блок А заполняется вручную: чек-лист 2.2 протокола."
    ws["A16"] = "«Полный» считается автоматически: все четыре пункта = «Да»."
    for row in range(11, 17):
        ws.cell(row=row, column=1).alignment = Alignment(wrap_text=False)


def build_instructions(wb: Workbook) -> None:
    ws = wb.create_sheet("Инструкция")
    ws.column_dimensions["A"].width = 120
    lines = [
        ("Как размечать блок А", True),
        ("", False),
        ("Полный ответ на сводку содержит четыре пункта (протокол 2.2):", False),
        ("1. Последний звонок — дата верная, либо явно «звонков не было».", False),
        ("2. Обещание клиента — дата верная, либо «обещаний нет».", False),
        ("3. Динамика по всем срезам, где клиент встречается, с верными категориями.", False),
        ("4. Итог последнего среза: количество непереданных, бейджи, в пуле или нет.", False),
        ("", False),
        ("В колонках «Звонки», «Обещание», «Динамика», «Итог» выберите «Да» или «Нет».", False),
        ("Колонка «Полный» посчитается сама.", False),
        ("", False),
        ("Факт-ошибка — дата, число или утверждение, противоречащее эталону:", False),
        ("неверный код клиента, выдуманный звонок или обещание, неверная категория.", False),
        ("Пишите числом в колонку «Факт-ошибок». Ноль — ошибок нет.", False),
        ("", False),
        ("Колонка «Последний срез (сверка)» — контрольные значения из данных:", False),
        ("с ними сверяйте итог ответа. Если модель взяла состояние предыдущего среза,", False),
        ("это видно сразу.", False),
        ("", False),
        ("Сводка по моделям считается на листе «Сводка».", False),
    ]
    for row, (text, bold) in enumerate(lines, start=1):
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(bold=bold, size=13 if bold else 11)
        cell.alignment = Alignment(wrap_text=True, vertical="top")


def main() -> None:
    questions = load_questions()
    scoring = load_scoring()
    models = []
    for model_dir in sorted(p for p in OUT.iterdir() if p.is_dir()):
        records = load_records(model_dir)
        a_records = [r for r in records if r["block"] == "A"]
        if not a_records:
            continue
        # deepseek:deepseek-flash -> deepseek-flash, ollama:qwen3.5:2b -> qwen3.5:2b
        display = a_records[0]["model"].split(":", 1)[-1]
        models.append((display, model_dir.name, records))

    if not models:
        raise SystemExit("нет результатов в scripts/h03/out — сначала запустите прогон")

    wb = Workbook()
    wb.remove(wb.active)

    sheets: dict[str, tuple[str, list[dict]]] = {}
    for display, title, records in models:
        a_records = [r for r in records if r["block"] == "A"]
        build_model_sheet(wb, title, a_records, questions, scoring.get(title, {}))
        sheets[display] = (title, records)

    build_summary(wb, sheets)
    build_instructions(wb)

    path = OUT / "h03_scoring.xlsx"
    try:
        wb.save(path)
    except PermissionError:
        # файл открыт в Excel — не ломаемся, пишем рядом
        path = OUT / "h03_scoring_filled.xlsx"
        wb.save(path)
        print("h03_scoring.xlsx открыт в Excel — сохранил рядом")
    print(f"готово: {path}")


if __name__ == "__main__":
    main()
