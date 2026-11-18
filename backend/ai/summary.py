"""Функция 1: сводка по клиенту для оператора перед звонком.

Принцип: все факты считает код и отдаёт модели готовым JSON. Модель только
пересказывает. Если факта в JSON нет — она обязана сказать «нет данных».
"""
from __future__ import annotations

import json
from typing import Any

from ai.providers import LLMProvider
from ai.schemas import ClientView

SYSTEM_PROMPT = """Ты — помощник оператора сервиса контроля передачи оригиналов документов.
Тебе дан JSON с фактами по одному клиенту. Отвечай ТОЛЬКО по этим фактам.

Правила:
1. Не добавляй ничего, чего нет в JSON: ни дат, ни звонков, ни чисел, ни событий.
2. Если сведений нет (контакты, суммы, авторы, даты претензий) — скажи «нет данных».
3. Говори «непереданные документы». Слова «долг», «задолженность», «должник» не используй.
4. Структура ответа: ЗВОНКИ, ДИНАМИКА, ИТОГ.
   - ЗВОНКИ: дата последнего звонка и обещание клиента, либо «звонков не было».
   - ДИНАМИКА: по каждому срезу — missing/total, доля в %, признак изменения и итоговая категория.
   - ИТОГ: состояние на последнем срезе, бейджи, в пуле обзвона или нет.
5. Не пересчитывай проценты иначе, чем в JSON. Пиши кратко, без вступлений.
"""


def build_facts(client: ClientView) -> dict[str, Any]:
    """Факты для модели. Всё, чего здесь нет, модель знать не может."""
    last = client.last
    return {
        "client": {
            "kcr_code": client.code,
            "organization": client.name,
            "inn": client.inn or None,
            "kpp": client.kpp,
            "client_type": client.client_type,
            "connected_at": client.connected_at.isoformat() if client.connected_at else None,
            "do_not_call": client.do_not_call,
            "stage": client.stage,
        },
        "calls": {
            "has_calls": client.last_call_date is not None,
            "last_call_date": client.last_call_date.isoformat() if client.last_call_date else None,
            "promised_date": client.promised_date.isoformat() if client.promised_date else None,
        },
        "snapshots": [s.to_dict() for s in client.snapshots],
        "current": None if last is None else {
            "slice_id": last.slice_id,
            "date": last.date.isoformat(),
            "missing": last.missing,
            "total": last.total,
            "share": None if last.share is None else round(last.share, 2),
            "category": last.category,
            "badges": client.badges,
            "in_pool": last.in_pool,
        },
    }


def summarize_client(client: ClientView, question: str, provider: LLMProvider) -> str:
    """Сводка по клиенту. Только чтение, ничего не меняет."""
    facts = build_facts(client)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Факты в JSON:\n"
                + json.dumps(facts, ensure_ascii=False, indent=2)
                + "\n\nВопрос:\n"
                + question
            ),
        },
    ]
    return provider.chat(messages, temperature=0.0, max_tokens=900)
