"""Функция 2: выборка клиентов по запросу словами для администратора.

Развилка гипотезы (Р-05): модель подбирает условия фильтра, клиентов отбирает
код. Модель не видит список клиентов и не может назвать «лишний» код.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from ai.providers import LLMProvider, ProviderError
from ai.schemas import (
    CHANGE_VALUES,
    FILTER_FIELDS,
    ClientFilter,
    ClientView,
    FilterError,
    apply_filter,
)

_FIELDS_TEXT = "\n".join(f"- {name}: {desc}" for name, desc in FILTER_FIELDS.items())
_CHANGES_TEXT = ", ".join(f"«{value}»" for value in CHANGE_VALUES)

SEARCH_SYSTEM_PROMPT = (
    "Ты превращаешь запрос администратора на русском языке в условия фильтра "
    "по клиентам. Ты НЕ выбираешь клиентов и НЕ называешь коды — это сделает код "
    "по твоим условиям.\n\n"
    "Верни ТОЛЬКО JSON вида:\n"
    '{"filter": { ... }, "explanation": "какие условия выбраны, одной фразой"}\n\n'
    "Доступные поля фильтра (другие использовать нельзя):\n"
    + _FIELDS_TEXT
    + "\n\nПравила:\n"
    "- Все условия внутри filter объединяются через И.\n"
    "- Даты — строка YYYY-MM-DD.\n"
    "- «Последний срез» — самый поздний срез клиента; «сейчас» — последний срез.\n"
    "- last_call_before: подходит и клиент, которому вообще не звонили.\n"
    "- Добавляй только те условия, о которых прямо сказано в запросе.\n"
    "- share_last_gt — число в процентах: «больше 25%» → 25, а не 0.25.\n"
    "- stage: используй только эти названия, дословно: «Выявлены непереданные документы», "
    "«Первый звонок», «Повторная проверка», «Претензия».\n"
    "- Признак изменения принимает только значения: " + _CHANGES_TEXT + ".\n"
    '- Если запрос нельзя выразить этими полями, верни {"filter": null, '
    '"explanation": "причина"}.\n'
    "- Никакого текста вне JSON."
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass
class SearchPlan:
    """Что вернула модель и что из этого применил код."""

    filter: ClientFilter | None
    explanation: str
    raw: str


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = _FENCE.sub("", text.strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ProviderError(f"модель вернула не JSON: {text[:200]!r}") from exc
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc2:
            raise ProviderError(f"модель вернула битый JSON: {text[:200]!r}") from exc2
    if not isinstance(data, dict):
        raise ProviderError("ожидался JSON-объект")
    return data


def parse_search(query: str, provider: LLMProvider, *,
                 today: date | None = None, context: str | None = None) -> SearchPlan:
    """Запрос словами → условия фильтра. Клиентов выбирает вызывающий код."""
    today_text = (today or date.today()).isoformat()
    reference = ""
    if context:
        reference = (
            "\n\nСправочно (это НЕ условия запроса; применяй только если запрос прямо об этом):\n"
            + context
        )
    messages = [
        {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": f"Сегодня {today_text}.{reference}\n\nЗапрос: {query}"},
    ]
    raw = provider.chat(messages, temperature=0.0, max_tokens=500, json_mode=True)
    data = _extract_json(raw)

    explanation = str(data.get("explanation") or "").strip()
    filter_data = data.get("filter", "missing")
    if filter_data is None:
        return SearchPlan(filter=None, explanation=explanation or "запрос не выражается фильтром", raw=raw)
    if filter_data == "missing":
        raise ProviderError("в ответе нет поля filter")
    try:
        flt = ClientFilter.from_dict(filter_data)
    except FilterError as exc:
        raise ProviderError(f"некорректный фильтр: {exc}") from exc
    return SearchPlan(filter=flt, explanation=explanation, raw=raw)


def search_clients(clients: list[ClientView], query: str, provider: LLMProvider, *,
                   today: date | None = None,
                   context: str | None = None) -> tuple[list[ClientView], SearchPlan]:
    """Полный путь: модель → условия → код → клиенты."""
    plan = parse_search(query, provider, today=today, context=context)
    if plan.filter is None:
        return [], plan
    return apply_filter(clients, plan.filter), plan
