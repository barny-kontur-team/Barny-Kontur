# -*- coding: utf-8 -*-
"""
H-02 · Скрипт расчёта признаков (модель Б) для сервиса контроля передачи
оригиналов документов КЦР (СКБ Контур).

Модель Б (проверяемая в H-02): по каждому клиенту в каждом срезе хранятся
ТРИ отдельных признака + дата первого появления:
  1) change    — изменение между срезами: одно из
                 «Нет сравнения», «Все переданы», «Появился впервые»,
                 «Уменьшается», «Не меняется или растёт», «Повторное появление»;
  2) is_novice — «новичок» (признак клиента, а не состояние);
  3) is_chronic— «хронический» (ситуация сохраняется длительное время);
  + first_appearance — срез и дата первого появления клиента.

Модель А (для сравнения): одно поле «категория» у клиента (последнее значение).

Правила расчёта — из ТЗ и контрольной книги H-01/H-02 (лист «06 Правила»):
  - Ключ клиента: код КЦР.
  - Опорный total: первый срез клиента в периоде; в повторных срезах периода
    опорный total не меняется, даже если пришло иное значение.
  - Новичок: дата подключения > дата среза − 6 календарных месяцев.
  - Хронический: предыдущий квартал имеет непереданные документы (последний срез клиента в
    предыдущем квартале с not>0); в текущем квартале «не было нулей»
    (not>0 во всех срезах квартала); этап работы дальше «Выявлены
    непереданные документы».
  - Изменение: относительно предыдущего среза клиента (в штуках, не в
    процентах; в том числе между кварталами, в том числе после пропуска).
  - Итоговая категория по приоритету: Нет сравнения → Нет данных →
    Хронический → Новичок → признак изменения.
  - Пул обзвона: not>0 и total>0 и (доля ≥ 5% или новичок) и не «Не работать».
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------

# Признак изменения (5 вариантов изменения + служебное «Нет сравнения»)
NO_PREVIOUS = "Нет сравнения"
ALL_PASSED = "Все переданы"
FIRST_TIME = "Появился впервые"
DECREASING = "Уменьшается"
NOT_DECREASING = "Не меняется или растёт"
RECURRED = "Повторное появление"

CHANGE_VALUES = (ALL_PASSED, FIRST_TIME, DECREASING, NOT_DECREASING, RECURRED)

# Порядок этапов работы (дальше «Выявлены непереданные документы» — индекс > 0)
STAGE_ORDER = [
    "Выявлены непереданные документы",
    "Первый звонок",
    "Повторная проверка",
    "Претензия",
]
FIRST_STAGE = STAGE_ORDER[0]

NO_DATA = "Нет данных"
CHRONIC = "Хронический"
NOVICE = "Новичок"

POOL_THRESHOLD_PCT = 5.0
NOVICE_MONTHS = 6


def months_before(d: date, months: int) -> date:
    """Дата минус N календарных месяцев (день фиксируется, 31→последний день)."""
    m = d.month - months
    y = d.year
    while m <= 0:
        m += 12
        y -= 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def stage_rank(stage: Optional[str]) -> int:
    """Ранг этапа; неизвестный этап считается самым ранним."""
    if not stage:
        return -1
    stage = stage.strip()
    for i, s in enumerate(STAGE_ORDER):
        if stage.startswith(s[:20]):
            return i
    return -1


def previous_quarter(period: str) -> Optional[str]:
    """«II кв. 2026» -> «I кв. 2026» римскими цифрами; None для I квартала."""
    roman = ["I", "II", "III", "IV"]
    try:
        q, y = [p.strip() for p in period.replace("кв.", "").split()]
        i = roman.index(q)
        year = int(y)
    except (ValueError, AttributeError):
        return None
    if i == 0:
        return None
    return f"{roman[i-1]} кв. {year}"


# ---------------------------------------------------------------------------
# Структуры данных (модель Б)
# ---------------------------------------------------------------------------


@dataclass
class Client:
    code: str
    connect_date: Optional[date] = None
    do_not_call: bool = False          # «Не включать в работу»
    stage: Optional[str] = None        # этап работы на дату среза (фикстура)
    first_appearance: Optional[dict] = field(default=None)  # {slice_id, date}


@dataclass
class SliceRow:
    """Хранимая строка модели Б: три признака на срез + опорные значения."""
    slice_id: str
    period: str                        # напр. «II кв. 2026»
    slice_date: date
    code: str
    total_ref: Optional[int]           # опорный total периода
    not_transferred: int               # не передано документов
    change: str                        # признак изменения (модель Б, признак 1)
    is_novice: bool                    # признак 2
    is_chronic: bool                   # признак 3
    # итоговая категория выводится приоритетом, но тоже сохраняется для UI:
    category: str = ""

    def __post_init__(self) -> None:
        self.category = self.resolve_category()

    def resolve_category(self) -> str:
        """Итоговая категория: Нет сравнения → Нет данных → Хронический →
        Новичок (только при not>0: «новичок не отправил все документы») →
        признак изменения."""
        if self.change == NO_PREVIOUS:
            return NO_PREVIOUS
        if not self.total_ref:
            return NO_DATA
        if self.is_chronic:
            return CHRONIC
        if self.is_novice and self.not_transferred > 0:
            return NOVICE
        return self.change


@dataclass
class RawSlice:
    """Сырой срез (вход импорта): одна строка файла среза."""
    slice_id: str
    period: str
    slice_date: date
    code: str
    total: Optional[int]               # «Документов всего» (может быть пустым)
    not_transferred: Optional[int]     # «Не передано документов»
    stage: Optional[str] = None        # этап работы на дату среза (если задан)


# ---------------------------------------------------------------------------
# Расчёт признаков (модель Б)
# ---------------------------------------------------------------------------


class FeatureCalculator:
    """Считает признаки по срезам в порядке их дат.

    Использование:
        calc = FeatureCalculator(clients)
        rows = calc.process(raw_slices)   # raw_slices отсортированы по дате
    """

    def __init__(self, clients: dict[str, Client]):
        self.clients = clients
        # состояние по клиенту между срезами:
        self.total_ref: dict[str, Optional[int]] = {}       # опорный total по (код, период)
        self.last_not: dict[str, int] = {}                  # not предыдущего среза клиента
        self.had_missing_before: dict[str, bool] = {}          # были ли непереданные документы когда-либо раньше
        self.seen_in_period: dict[tuple[str, str], list[int]] = {}

    # -- признак 1: изменение между срезами ---------------------------------

    def _change(self, code: str, prev_not: Optional[int], not_now: int) -> str:
        if prev_not is None:
            return NO_PREVIOUS
        if not_now == 0:
            return ALL_PASSED
        if prev_not == 0:
            if self.had_missing_before.get(code):
                return RECURRED
            return FIRST_TIME
        if not_now < prev_not:
            return DECREASING
        return NOT_DECREASING

    # -- признак 3: хронический ---------------------------------------------

    def _chronic(self, code: str, period: str, not_now: int,
                 seen_period_nots: list[int], stage: Optional[str] = None) -> bool:
        # этап дальше «Выявлены непереданные документы» (на дату среза)
        client = self.clients.get(code)
        current_stage = stage if stage is not None else (client.stage if client else None)
        if stage_rank(current_stage) <= stage_rank(FIRST_STAGE):
            return False
        # в текущем квартале «не было нулей» (включая текущий срез)
        if any(n == 0 for n in seen_period_nots):
            return False
        # предыдущий квартал имеет непереданные документы: последний срез клиента в нём с not>0
        prev_period = previous_quarter(period)
        if prev_period is None:
            return False
        prev_nots = self.seen_in_period.get((code, prev_period))
        if not prev_nots or prev_nots[-1] <= 0:
            return False
        return not_now > 0

    # -- основной проход -----------------------------------------------------

    def process(self, raw_slices: list[RawSlice]) -> list[SliceRow]:
        results: list[SliceRow] = []
        for raw in raw_slices:
            client = self.clients.get(raw.code)
            if client is None:
                continue  # неизвестный клиент — ошибка импорта (кейс H-01), не H-02

            # дата первого появления клиента
            if client.first_appearance is None:
                client.first_appearance = {
                    "slice_id": raw.slice_id, "date": raw.slice_date.isoformat()
                }

            # опорный total: первый срез клиента в периоде
            key = (raw.code, raw.period)
            if key not in self.total_ref:
                self.total_ref[key] = raw.total
            total_ref = self.total_ref[key]

            not_now = raw.not_transferred or 0

            # срезы клиента в текущем квартале (для «не было нулей»)
            seen = self.seen_in_period.setdefault(key, [])
            seen.append(not_now)

            prev_not = self.last_not.get(raw.code)

            change = self._change(raw.code, prev_not, not_now)
            is_novice = bool(
                client.connect_date
                and client.connect_date > months_before(raw.slice_date, NOVICE_MONTHS)
            )
            is_chronic = self._chronic(raw.code, raw.period, not_now, seen, stage=raw.stage)

            row = SliceRow(
                slice_id=raw.slice_id, period=raw.period, slice_date=raw.slice_date,
                code=raw.code, total_ref=total_ref, not_transferred=not_now,
                change=change, is_novice=is_novice, is_chronic=is_chronic,
            )
            results.append(row)

            # обновляем состояние
            self.had_missing_before[raw.code] = self.had_missing_before.get(raw.code, False) or not_now > 0
            self.last_not[raw.code] = not_now

        return results

    # -- пул обзвона ---------------------------------------------------------

    @staticmethod
    def in_call_pool(row: SliceRow, client: Client) -> bool:
        """not>0 и total>0 и (доля ≥ 5% или новичок) и не «Не работать»."""
        if client.do_not_call or row.not_transferred <= 0:
            return False
        if not row.total_ref:
            return False
        share = row.not_transferred / row.total_ref * 100.0
        return share >= POOL_THRESHOLD_PCT - 1e-9 or row.is_novice


# ---------------------------------------------------------------------------
# Модель А: одно поле «категория» у клиента (последнее значение)
# ---------------------------------------------------------------------------

CATEGORY_VALUES = (
    ALL_PASSED, FIRST_TIME, DECREASING, NOT_DECREASING, RECURRED,
    CHRONIC, NOVICE,  # 7 категорий заказчика (без «Нет сравнения»/«Нет данных»)
)


class ModelA:
    """Модель А: у клиента ровно одно поле «категория», перезаписывается."""

    def __init__(self) -> None:
        self.category: dict[str, str] = {}

    def store(self, code: str, row: SliceRow) -> None:
        self.category[code] = row.category  # перезапись прошлого значения

    def past_state(self, code: str, slice_id: str) -> None:
        """Восстановление состояния на прошлый срез — невозможно."""
        return None


def model_b_tuple(row: SliceRow) -> tuple:
    """Полная запись состояния (сочетание признаков) в модели Б."""
    return (row.change, row.is_novice, row.is_chronic)
