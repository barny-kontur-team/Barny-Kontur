"""Модель данных ИИ-помощника: только чтение, без зависимостей от других модулей.

`ClientView` — то, что модуль `ai` получает на вход: клиент и его срезы в
готовом виде. Откуда взялись цифры (импорт, динамика) — не его дело.
`ClientFilter` — условия выборки, которые подбирает модель, а применяет код.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Признаки изменения между срезами (совпадают с scripts/h02/features.py)
NO_PREVIOUS = "Нет сравнения"
ALL_PASSED = "Все переданы"
FIRST_TIME = "Появился впервые"
DECREASING = "Уменьшается"
NOT_DECREASING = "Не меняется или растёт"
RECURRED = "Повторное появление"

CHANGE_VALUES = (ALL_PASSED, FIRST_TIME, DECREASING, NOT_DECREASING, RECURRED)

# Итоговые категории (выводятся из трёх признаков, см. ADR-0002)
NO_DATA = "Нет данных"
CHRONIC = "Хронический"
NOVICE = "Новичок"

POOL_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class SnapshotView:
    """Один срез клиента в готовом для показа виде."""

    slice_id: str
    period: str
    date: date
    missing: int
    total: int | None
    change: str
    is_novice: bool
    is_chronic: bool
    category: str
    in_pool: bool

    @property
    def share(self) -> float | None:
        """Доля непереданных, %. None — если опорный total неизвестен или 0."""
        if not self.total:
            return None
        return self.missing / self.total * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "period": self.period,
            "date": self.date.isoformat(),
            "missing": self.missing,
            "total": self.total,
            "share": None if self.share is None else round(self.share, 2),
            "change": self.change,
            "category": self.category,
            "is_novice": self.is_novice,
            "is_chronic": self.is_chronic,
            "in_pool": self.in_pool,
        }


@dataclass
class ClientView:
    """Клиент и его история срезов; звонки — из фикстуры (в сервисе — из calls)."""

    code: str
    name: str
    inn: str = ""
    kpp: str | None = None
    client_type: str | None = None
    connected_at: date | None = None
    do_not_call: bool = False
    stage: str | None = None
    last_call_date: date | None = None
    promised_date: date | None = None
    snapshots: list[SnapshotView] = field(default_factory=list)

    @property
    def last(self) -> SnapshotView | None:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def previous(self) -> SnapshotView | None:
        return self.snapshots[-2] if len(self.snapshots) > 1 else None

    @property
    def had_missing(self) -> bool:
        return any(s.missing > 0 for s in self.snapshots)

    @property
    def had_recurrence(self) -> bool:
        return any(s.change == RECURRED for s in self.snapshots)

    @property
    def is_novice_with_missing(self) -> bool:
        return any(s.is_novice and s.missing > 0 for s in self.snapshots)

    @property
    def badges(self) -> list[str]:
        """Бейджи последнего среза (для карточки и сводки)."""
        last = self.last
        if last is None:
            return []
        out = []
        if last.is_chronic:
            out.append(CHRONIC)
        # Конвенция показа (ADR-0002): «Новичок» виден только при not > 0
        if last.is_novice and last.missing > 0:
            out.append(NOVICE)
        if self.do_not_call:
            out.append("Не включать в работу")
        return out


class FilterError(ValueError):
    """Модель вернула условия, которые код не может применить."""


# Поля фильтра и их смысл. Порядок и названия фиксированы: их видит модель.
FILTER_FIELDS: dict[str, str] = {
    "share_last_gt": "доля непереданных на последнем срезе, число в процентах 0–100 (строго больше)",
    "in_pool_last": "клиент в пуле обзвона на последнем срезе",
    "novice_last": "признак «Новичок» на последнем срезе",
    "novice_with_missing_ever": "был новичком хотя бы в одном срезе, где missing > 0",
    "chronic_last": "признак «Хронический» на последнем срезе",
    "last_call_before": "последний звонок раньше даты (нет звонков — подходит)",
    "stage": "этап работы, одно из допустимых названий (см. список ниже)",
    "connected_on_or_after": "дата подключения не раньше указанной",
    "had_missing_ever": "missing > 0 хотя бы в одном срезе",
    "missing_zero_last": "на последнем срезе missing = 0",
    "no_recurrence_ever": "ни в одном срезе не было «Повторное появление»",
    "total_zero_last": "всего документов на последнем срезе = 0, поэтому доля не считается (статус «Нет данных»)",
    "do_not_call": "признак «Не включать в работу»",
    "last_change_equals": "признак изменения на последнем срезе равен значению",
    "last_two_changes_equal": "два последних среза подряд с этим признаком изменения",
}

def _as_bool(name: str, value: Any) -> bool:
    """Строгий bool, но мелкие модели любят «true» строкой — принимаем."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "да"):
            return True
        if lowered in ("false", "no", "нет"):
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise FilterError(f"{name}: ожидается true/false")


def _as_percent(value: Any) -> float:
    """Доля в процентах: принимаем 25, 25.0 и «25%»; 0.25 — уже ошибка модели."""
    if isinstance(value, bool):
        raise FilterError("share_last_gt: ожидается число")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(",", ".").strip()
        try:
            number = float(cleaned)
        except ValueError as exc:
            raise FilterError(f"share_last_gt: ожидается число, получено {value!r}") from exc
    else:
        raise FilterError("share_last_gt: ожидается число")
    if not 0 <= number <= 100:
        raise FilterError(f"share_last_gt: ожидается процент 0–100, получено {number}")
    return number


_BOOL_FIELDS = ("in_pool_last", "novice_last", "novice_with_missing_ever", "chronic_last",
                "had_missing_ever", "missing_zero_last", "no_recurrence_ever",
                "total_zero_last", "do_not_call")
_DATE_FIELDS = ("last_call_before", "connected_on_or_after")
_CHANGE_FIELDS = ("last_change_equals", "last_two_changes_equal")


@dataclass(frozen=True)
class ClientFilter:
    """Условия выборки. Пустое поле — условие не задано."""

    share_last_gt: float | None = None
    in_pool_last: bool | None = None
    novice_last: bool | None = None
    novice_with_missing_ever: bool | None = None
    chronic_last: bool | None = None
    last_call_before: date | None = None
    stage: str | None = None
    connected_on_or_after: date | None = None
    had_missing_ever: bool | None = None
    missing_zero_last: bool | None = None
    no_recurrence_ever: bool | None = None
    total_zero_last: bool | None = None
    do_not_call: bool | None = None
    last_change_equals: str | None = None
    last_two_changes_equal: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClientFilter":
        """Строгая сборка из JSON модели: неизвестное поле — ошибка, не догадка."""
        if not isinstance(data, dict):
            raise FilterError("filter должен быть объектом JSON")

        unknown = set(data) - set(FILTER_FIELDS)
        if unknown:
            raise FilterError(f"неизвестные поля фильтра: {sorted(unknown)}")

        kwargs: dict[str, Any] = {}
        for key, value in data.items():
            if value is None:
                continue
            if key in _BOOL_FIELDS:
                kwargs[key] = _as_bool(key, value)
            elif key in _DATE_FIELDS:
                if not isinstance(value, str):
                    raise FilterError(f"{key}: ожидается дата YYYY-MM-DD")
                try:
                    kwargs[key] = date.fromisoformat(value)
                except ValueError as exc:
                    raise FilterError(f"{key}: неверная дата {value!r}") from exc
            elif key in _CHANGE_FIELDS:
                if value not in CHANGE_VALUES:
                    raise FilterError(f"{key}: недопустимое значение {value!r}")
                kwargs[key] = value
            elif key == "share_last_gt":
                kwargs[key] = _as_percent(value)
            elif key == "stage":
                if not isinstance(value, str) or not value.strip():
                    raise FilterError("stage: ожидается непустая строка")
                kwargs[key] = value.strip()
            else:  # pragma: no cover — список полей закрыт FILTER_FIELDS
                raise FilterError(f"поле не поддержано: {key}")
        return cls(**kwargs)

    def is_empty(self) -> bool:
        return all(getattr(self, name) is None for name in FILTER_FIELDS)

    def describe(self) -> list[str]:
        """Человекочитаемые условия — для отчёта и объяснения пользователю."""
        out: list[str] = []
        for name in FILTER_FIELDS:
            value = getattr(self, name)
            if value is None:
                continue
            out.append(f"{name}={value}")
        return out


def _stage_eq(actual: str | None, expected: str) -> bool:
    return (actual or "").strip().lower() == expected.strip().lower()


def matches(client: ClientView, flt: ClientFilter) -> bool:
    """Проверка одного клиента по всем заданным условиям."""
    last = client.last

    if flt.share_last_gt is not None:
        if last is None or last.share is None or last.share <= flt.share_last_gt:
            return False
    if flt.in_pool_last is not None:
        if last is None or last.in_pool != flt.in_pool_last:
            return False
    if flt.novice_last is not None:
        if last is None or last.is_novice != flt.novice_last:
            return False
    if flt.novice_with_missing_ever is not None:
        if client.is_novice_with_missing != flt.novice_with_missing_ever:
            return False
    if flt.chronic_last is not None:
        if last is None or last.is_chronic != flt.chronic_last:
            return False
    if flt.last_call_before is not None:
        if client.last_call_date is not None and client.last_call_date >= flt.last_call_before:
            return False
    if flt.stage is not None:
        if not _stage_eq(client.stage, flt.stage):
            return False
    if flt.connected_on_or_after is not None:
        if client.connected_at is None or client.connected_at < flt.connected_on_or_after:
            return False
    if flt.had_missing_ever is not None:
        if client.had_missing != flt.had_missing_ever:
            return False
    if flt.missing_zero_last is not None:
        if last is None or (last.missing == 0) != flt.missing_zero_last:
            return False
    if flt.no_recurrence_ever is not None:
        if client.had_recurrence == flt.no_recurrence_ever:
            return False
    if flt.total_zero_last is not None:
        total = last.total if last else None
        if ((total or 0) == 0) != flt.total_zero_last:
            return False
    if flt.do_not_call is not None:
        if client.do_not_call != flt.do_not_call:
            return False
    if flt.last_change_equals is not None:
        if last is None or last.change != flt.last_change_equals:
            return False
    if flt.last_two_changes_equal is not None:
        prev = client.previous
        if prev is None or last is None:
            return False
        if last.change != flt.last_two_changes_equal or prev.change != flt.last_two_changes_equal:
            return False
    return True


def apply_filter(clients: list[ClientView], flt: ClientFilter) -> list[ClientView]:
    """Отбор клиентов кодом. Модель сюда не допускается."""
    return sorted((c for c in clients if matches(c, flt)), key=lambda c: c.code)
