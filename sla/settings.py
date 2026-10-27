"""Настройки из переменных окружения - одно место на весь проект."""
import os
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Settings:
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "delivery_sla"
    db_user: str = "sla"
    db_password: str = ""
    carrier_url: str = "http://localhost:8090"
    sla_target: float = 95.0
    # фиксированное «текущее время» для повторяемых отчётов; пусто - настоящее время
    report_now: Optional[str] = None

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        values = {}
        for f in fields(cls):
            raw = env.get(f.name.upper())
            if raw in (None, ""):
                continue
            values[f.name] = int(raw) if f.type is int else float(raw) if f.type is float else raw
        return cls(**values)

    def now(self) -> datetime:
        if self.report_now:
            return datetime.fromisoformat(self.report_now)
        return datetime.now().replace(second=0, microsecond=0)
