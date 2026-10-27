"""Сценарии конвейера: приём строк заказов (проверка -> запись) и пересчёт SLA с агрегацией.
Хранилище, календарь и время передаются параметрами."""
import logging
from dataclasses import dataclass, field
from datetime import datetime

from .calendar import WorkCalendar
from .metrics import by_day_zone, evaluate
from .rules import validate_row

log = logging.getLogger(__name__)


@dataclass
class IngestReport:
    accepted: int = 0
    added: int = 0
    updated: int = 0
    rejected: list = field(default_factory=list)   # (номер строки, номер заказа, исходная строка, причина)


def raw_line(row: dict) -> str:
    return ";".join(str(v or "") for v in row.values())


def ingest(rows, repo, now: datetime, source: str = "api", kind: str = "api",
           validate=validate_row) -> IngestReport:
    """rows: список (номер строки, словарь полей). Повтор номера заказа в одном пакете отклоняется."""
    zones = repo.zones()
    batch = repo.start_batch(source, kind)
    report = IngestReport()
    good, first_line = [], {}
    for line_no, row in rows:
        order, errors = validate(row, zones, now)
        if order is not None and order.order_no in first_line:
            errors = [f"повтор номера заказа {order.order_no} (впервые в строке {first_line[order.order_no]})"]
            order = None
        if errors:
            report.rejected.append((line_no, (row.get("order_no") or "").strip(), raw_line(row), "; ".join(errors)))
            continue
        first_line[order.order_no] = line_no
        good.append(order)
    report.added, report.updated = repo.upsert_orders(good, batch)
    report.accepted = len(good)
    repo.add_rejected(batch, report.rejected)
    repo.finish_batch(batch, report.accepted, len(report.rejected))
    log.info("пакет %s (%s): принято %d (новых %d, обновлено %d), отклонено %d",
             batch, source, report.accepted, report.added, report.updated, len(report.rejected))
    return report


def recompute(repo, now: datetime, calendar: WorkCalendar = None) -> dict:
    """Шаг агрегации: исход SLA по каждому заказу и сводка по дням и зонам. Возвращает сводку."""
    calendar = calendar or WorkCalendar(holidays=repo.holidays())
    zones = repo.zones()
    results = [evaluate(o, zones[o.zone], calendar, now) for o in repo.orders()]
    daily = by_day_zone(results)
    repo.save_results(results)
    repo.save_daily(daily)
    log.info("пересчёт SLA на %s: заказов %d, строк сводки %d", now.strftime("%Y-%m-%d %H:%M"),
             len(results), len(daily))
    return daily
