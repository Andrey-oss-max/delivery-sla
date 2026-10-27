"""Расчёт SLA: срок доставки заказа, исход по заказу и сводные показатели по группе заказов."""
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Optional

from .calendar import WorkCalendar
from .domain import EXCLUDED, IN_PROGRESS, LATE, ON_TIME, OPEN_LATE, Order, SlaResult, Zone


def deadline(order: Order, zone: Zone, cal: WorkCalendar) -> datetime:
    if order.reschedule_to is not None:
        return order.reschedule_to
    if order.tariff == "express":
        return cal.express_deadline(order.created_at, zone.express_hours)
    return cal.standard_deadline(order.created_at, zone.standard_days)


def _hours(delta) -> float:
    return round(delta.total_seconds() / 3600, 2)


def evaluate(order: Order, zone: Zone, cal: WorkCalendar, now: datetime) -> SlaResult:
    due = deadline(order, zone, cal)
    if order.status == "cancelled":
        return SlaResult(order.order_no, order.zone, due, EXCLUDED)
    if order.status == "delivered":
        hours = _hours(order.delivered_at - order.created_at)
        if order.delivered_at <= due:
            return SlaResult(order.order_no, order.zone, due, ON_TIME, hours)
        return SlaResult(order.order_no, order.zone, due, LATE, hours, _hours(order.delivered_at - due))
    if now > due:
        return SlaResult(order.order_no, order.zone, due, OPEN_LATE, None, _hours(now - due))
    return SlaResult(order.order_no, order.zone, due, IN_PROGRESS)


def percentile(values, p: float) -> Optional[float]:
    """Процентиль методом ближайшего ранга: значение, не меньше которого p% выборки."""
    if not values:
        return None
    if not 0 < p <= 100:
        raise ValueError("p должно быть в (0; 100]")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


@dataclass(frozen=True)
class Summary:
    total: int
    on_time: int
    late: int
    open_late: int
    in_progress: int
    excluded: int
    sla_pct: Optional[float]      # доля вовремя среди учитываемых, %
    p50_h: Optional[float]
    p90_h: Optional[float]
    avg_delay_h: Optional[float]

    @property
    def counted(self) -> int:
        """Заказы, по которым SLA уже определён: доставленные и просроченные в пути."""
        return self.on_time + self.late + self.open_late


def summarize(results: Iterable[SlaResult]) -> Summary:
    results = list(results)
    n = {k: 0 for k in (ON_TIME, LATE, OPEN_LATE, IN_PROGRESS, EXCLUDED)}
    for r in results:
        n[r.outcome] += 1
    counted = n[ON_TIME] + n[LATE] + n[OPEN_LATE]
    hours = [r.hours for r in results if r.hours is not None]
    delays = [r.delay_h for r in results if r.delay_h is not None]
    return Summary(
        total=len(results), on_time=n[ON_TIME], late=n[LATE], open_late=n[OPEN_LATE],
        in_progress=n[IN_PROGRESS], excluded=n[EXCLUDED],
        sla_pct=round(100 * n[ON_TIME] / counted, 1) if counted else None,
        p50_h=percentile(hours, 50), p90_h=percentile(hours, 90),
        avg_delay_h=round(sum(delays) / len(delays), 2) if delays else None,
    )


def group(results: Iterable[SlaResult], key: Callable[[SlaResult], object]) -> dict:
    """Агрегация: ключ группы -> Summary. Ключи отсортированы."""
    buckets = defaultdict(list)
    for r in results:
        buckets[key(r)].append(r)
    return {k: summarize(buckets[k]) for k in sorted(buckets)}


def by_day_zone(results):
    return group(results, lambda r: (r.day, r.zone))


def by_zone(results):
    return group(results, lambda r: r.zone)


def by_day(results):
    return group(results, lambda r: r.day)
