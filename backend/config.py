"""Настройки сервиса — из переменных окружения (см. .env.example)."""
import os


class Settings:
    """Простое чтение окружения без внешних зависимостей."""

    def __init__(self) -> None:
        self.app_name: str = "Barny-Kontur KCR API"
        self.database_url: str = os.getenv(
            "DATABASE_URL",
            # по умолчанию — локальный файл, чтобы скелет поднимался без Docker;
            # в docker-compose задаётся PostgreSQL
            "sqlite:///./kcr.db",
        )


settings = Settings()
