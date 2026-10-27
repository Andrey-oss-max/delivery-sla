"""Предметные объекты: зона доставки, заказ, результат расчёта SLA. Только стандартная библиотека."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

CHANNELS = ("site", "marketplace", "phone")
TARIFFS = ("express", "standard")
STATUSES = ("delivered", "in_transit", "cancelled")

# исходы расчёта SLA по одному заказу
ON_TIME = "on_time"          # доставлен не позже срока
LATE = "late"                # доставлен после срока
OPEN_LATE = "open_late"      # ещё не доставлен, а срок уже прошёл
IN_PROGRESS = "in_progress"  # ещё не доставлен, срок не наступил - в SLA не учитывается
EXCLUDED = "excluded"        # отменён - в SLA не учитывается
OUTCOMES = (ON_TIME, LATE, OPEN_LATE, IN_PROGRESS, EXCLUDED)


@dataclass(frozen=True)
class Zone:
    code: str
    name: str
    express_hours: int   # срок экспресс-доставки, календарные часы
    standard_days: int   # срок стандартной доставки, рабочие дни


@dataclass(frozen=True)
class Order:
    order_no: str
    channel: str
    zone: str
    tariff: str
    created_at: datetime
    status: str
    delivered_at: Optional[datetime] = None
    # новое время, согласованное с клиентом по его просьбе: срок SLA переносится на него
    reschedule_to: Optional[datetime] = None


@dataclass(frozen=True)
class SlaResult:
    order_no: str
    zone: str
    deadline: datetime
    outcome: str
    hours: Optional[float] = None    # фактическое время доставки, ч
    delay_h: Optional[float] = None  # просрочка, ч (для late и open_late)

    @property
    def day(self) -> date:
        """День, к которому относится заказ в отчётах, - день срока доставки."""
        return self.deadline.date()


class UnknownZone(Exception):
    pass


class RepositoryError(Exception):
    pass
