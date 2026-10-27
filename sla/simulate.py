"""Генератор потока заказов с внедрением сбоев. Одинаковый seed - одинаковые данные."""
import random
from datetime import datetime, timedelta

from .calendar import WorkCalendar
from .metrics import deadline
from .domain import Order

# доля опозданий по зонам: удалённые зоны опаздывают чаще
LATE_RATE = {"CTR": 0.03, "LEN": 0.05, "MOS": 0.06, "PRG": 0.12, "OBL": 0.2}
FAULTS = ("unknown_zone", "before_created", "bad_date", "bad_tariff", "future", "duplicate", "no_delivery_time")


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def generate(zones: dict, count: int, now: datetime, days: int = 14, seed: int = 42,
             fault_rate: float = 0.08, calendar: WorkCalendar = None):
    """Возвращает список (номер строки, словарь полей) в формате строк реестра."""
    rnd = random.Random(seed)
    cal = calendar or WorkCalendar()
    codes = sorted(zones)
    rows, issued = [], []
    for i in range(1, count + 1):
        zone = rnd.choice(codes)
        created = now - timedelta(days=rnd.uniform(0.2, days))
        created = created.replace(hour=rnd.randint(8, 20), minute=rnd.choice((0, 10, 15, 25, 30, 40, 45, 50)),
                                  second=0, microsecond=0)
        if created > now:
            created -= timedelta(days=1)
        tariff = "express" if rnd.random() < 0.3 else "standard"
        order_no = f"D-{created:%y%m%d}-{seed % 100:02d}{i:03d}"
        probe = Order(order_no, "site", zone, tariff, created, "in_transit")
        due = deadline(probe, zones[zone], cal)
        row = {"order_no": order_no, "channel": rnd.choice(("site", "site", "marketplace", "phone")),
               "zone": zone, "tariff": tariff, "created_at": _fmt(created), "delivered_at": "",
               "status": "delivered", "reschedule_to": ""}
        r = rnd.random()
        if r < 0.04:
            row["status"] = "cancelled"
        else:
            if r < 0.07:  # клиент попросил перенести доставку
                due = due + timedelta(days=1)
                row["reschedule_to"] = _fmt(due)
            if rnd.random() < LATE_RATE.get(zone, 0.08):
                delivered = due + timedelta(hours=rnd.uniform(0.5, 30))
            else:
                span = max((due - created).total_seconds() / 3600, 1.0)
                delivered = created + timedelta(hours=rnd.uniform(0.3, span) * rnd.uniform(0.5, 1.0))
            delivered = delivered.replace(second=0, microsecond=0)
            if delivered > now:
                row["status"] = "in_transit"
            else:
                row["delivered_at"] = _fmt(delivered)
        if rnd.random() < fault_rate:
            _inject(row, rnd.choice(FAULTS), rnd, now, issued)
        issued.append(row["order_no"])
        rows.append((i + 1, row))  # строка 1 - заголовок файла
    return rows


def _inject(row, fault, rnd, now, issued):
    if fault == "unknown_zone":
        row["zone"] = "ZZZ"
    elif fault == "before_created" and row["delivered_at"]:
        created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M")
        row["delivered_at"] = _fmt(created - timedelta(hours=rnd.randint(1, 5)))
    elif fault == "bad_date":
        row["created_at"] = row["created_at"].replace("-", "/", 1) + "?"
    elif fault == "bad_tariff":
        row["tariff"] = "turbo"
    elif fault == "future":
        row["created_at"] = _fmt(now + timedelta(days=2))
        row["delivered_at"], row["status"] = "", "in_transit"
    elif fault == "duplicate" and issued:
        row["order_no"] = rnd.choice(issued)
    elif fault == "no_delivery_time":
        row["status"], row["delivered_at"] = "delivered", ""
