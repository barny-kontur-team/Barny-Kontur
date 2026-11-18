"""Провайдеры модели. Один интерфейс — заменяемая модель (правило 7 AGENTS.md).

Сейчас: DeepSeek (внешний API) и Ollama (локально). Позже добавится внутренняя
модель Контура — тогда меняется только реализация, функции помощника те же.

Никаких секретов в коде: ключ берётся из окружения (`DEEPSEEK_API_KEY`).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

Message = dict[str, str]


class ProviderError(RuntimeError):
    """Модель недоступна или вернула не то, что просили."""


class LLMProvider(Protocol):
    """Минимальный интерфейс: сообщения на входе, текст на выходе."""

    name: str

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 900,
        json_mode: bool = False,
    ) -> str: ...


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str],
               timeout: float) -> dict[str, Any]:
    """POST с JSON и небольшими повторами на 429/5xx (для прогона, не для API)."""
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            last_error = ProviderError(f"HTTP {exc.code}: {detail}")
            if exc.code not in (429, 500, 502, 503, 504):
                break
        except urllib.error.URLError as exc:
            last_error = ProviderError(f"сеть недоступна: {exc.reason}")
        time.sleep(1.5 * (attempt + 1))
    raise last_error or ProviderError("неизвестная ошибка запроса")


@dataclass
class DeepSeekProvider:
    """DeepSeek, OpenAI-совместимый API. Ключ — из окружения или аргумента."""

    model: str = "deepseek-flash"
    api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    base_url: str = "https://api.deepseek.com"
    timeout: float = 120.0
    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.name = f"deepseek:{self.model}"
        if not self.api_key:
            raise ProviderError("не задан DEEPSEEK_API_KEY")

    def chat(self, messages: list[Message], *, temperature: float = 0.0,
             max_tokens: int = 900, json_mode: bool = False) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(
            f"{self.base_url.rstrip('/')}/chat/completions",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
            self.timeout,
        )
        try:
            return (data["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"неожиданный ответ DeepSeek: {data}") from exc


@dataclass
class OllamaProvider:
    """Локальная модель через Ollama.

    Важно: ходим в нативный /api/chat, а не в /v1/chat/completions —
    только там работает `think: false`. Иначе Qwen 3.5 уходит в reasoning
    и возвращает пустой content.
    """

    model: str = "qwen3.5:2b"
    base_url: str = field(default_factory=lambda: os.getenv(
        "OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    timeout: float = 300.0
    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.name = f"ollama:{self.model}"

    def chat(self, messages: list[Message], *, temperature: float = 0.0,
             max_tokens: int = 900, json_mode: bool = False) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(
            f"{self.base_url.rstrip('/')}/api/chat",
            payload,
            {},
            self.timeout,
        )
        try:
            return (data["message"].get("content") or "").strip()
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"неожиданный ответ Ollama: {data}") from exc


def build_provider(model: str, *, api_key: str | None = None) -> LLMProvider:
    """Выбор провайдера по имени модели: deepseek-* → API, остальное → Ollama."""
    if model.startswith("deepseek"):
        return DeepSeekProvider(model=model, api_key=api_key or os.getenv("DEEPSEEK_API_KEY", ""))
    return OllamaProvider(model=model)
