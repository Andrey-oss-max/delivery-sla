"""Общие данные для тестов: зоны, календарь, фиксированное «сейчас»."""
from datetime import date, datetime

from sla.calendar import WorkCalendar
from sla.domain import Order, Zone

NOW = datetime(2026, 11, 6, 18, 0)   # пятница
ZONES = {
    "CTR": Zone("CTR", "Центральный район", 3, 1),
    "OBL": Zone("OBL", "Калининградская область", 24, 3),
}
CAL = WorkCalendar(holidays=frozenset({date(2026, 11, 4)}))


def row(**kw):
    base = {"order_no": "D-1", "channel": "site", "zone": "CTR", "tariff": "express",
            "created_at": "2026-11-02 10:00", "delivered_at": "2026-11-02 12:00", "status": "delivered",
            "reschedule_to": ""}
    base.update(kw)
    return base


def order(**kw):
    base = dict(order_no="D-1", channel="site", zone="CTR", tariff="express",
                created_at=datetime(2026, 11, 2, 10, 0), status="delivered",
                delivered_at=datetime(2026, 11, 2, 12, 0))
    base.update(kw)
    return Order(**base)
