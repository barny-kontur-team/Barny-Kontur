"""ИИ-помощник (только чтение): сводка по клиенту и выборка словами.

Публичный интерфейс модуля. Модель подключается через `ai.providers`, поэтому
её можно заменить, не меняя функции помощника.
"""
from ai.providers import DeepSeekProvider, LLMProvider, OllamaProvider, ProviderError, build_provider
from ai.schemas import (
    ALL_PASSED,
    CHANGE_VALUES,
    CHRONIC,
    DECREASING,
    FIRST_TIME,
    NO_DATA,
    NO_PREVIOUS,
    NOT_DECREASING,
    NOVICE,
    RECURRED,
    ClientFilter,
    ClientView,
    FilterError,
    SnapshotView,
    apply_filter,
    matches,
)
from ai.search import SearchPlan, parse_search, search_clients
from ai.summary import build_facts, summarize_client

__all__ = [
    "ALL_PASSED",
    "CHANGE_VALUES",
    "CHRONIC",
    "DECREASING",
    "FIRST_TIME",
    "NO_DATA",
    "NO_PREVIOUS",
    "NOT_DECREASING",
    "NOVICE",
    "RECURRED",
    "ClientFilter",
    "ClientView",
    "DeepSeekProvider",
    "FilterError",
    "LLMProvider",
    "OllamaProvider",
    "ProviderError",
    "SearchPlan",
    "SnapshotView",
    "apply_filter",
    "build_facts",
    "build_provider",
    "matches",
    "parse_search",
    "search_clients",
    "summarize_client",
]
