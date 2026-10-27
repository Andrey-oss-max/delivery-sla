"""Правила проверки входной строки заказа. Чистые функции: словарь на входе - заказ или список ошибок на выходе."""
import re
from datetime import datetime, timedelta, timezone
from typing import Mapping

from .domain import CHANNELS, STATUSES, TARIFFS, Order, Zone

# все времена в системе - местное время Калининграда (UTC+2, без перехода на летнее время)
LOCAL_TZ = timezone(timedelta(hours=2))
MAX_DELIVERY = timedelta(days=60)
ORDER_NO = re.compile(r"^[A-Za-z0-9-]{1,32}$")
FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S")


def parse_dt(text: str) -> datetime:
    """Время из файла в местное время без пояса. Время с поясом переводится в UTC+2."""
    text = text.strip()
    for fmt in FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    dt = datetime.fromisoformat(text)  # ISO 8601, в том числе с 'T' и смещением
    if dt.tzinfo is not None:
        dt = dt.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return dt


def _dt(row, key, errors, label, required):
    value = (row.get(key) or "").strip()
    if not value:
        if required:
            errors.append(f"нет поля «{label}»")
        return None
    try:
        return parse_dt(value)
    except ValueError:
        errors.append(f"неверный формат времени «{label}»: {value}")
        return None


def validate_row(row: Mapping[str, str], zones: Mapping[str, Zone], now: datetime):
    """Возвращает (Order, []) для корректной строки или (None, [причины]) для отклонённой."""
    errors = []
    order_no = (row.get("order_no") or "").strip()
    if not order_no:
        errors.append("нет номера заказа")
    elif not ORDER_NO.match(order_no):
        errors.append(f"недопустимый номер заказа: {order_no}")

    channel = (row.get("channel") or "").strip().lower()
    if channel not in CHANNELS:
        errors.append(f"неизвестный канал: {channel or 'пусто'}")

    zone = (row.get("zone") or "").strip().upper()
    if not zone:
        errors.append("нет зоны доставки")
    elif zone not in zones:
        errors.append(f"неизвестная зона: {zone}")

    tariff = (row.get("tariff") or "").strip().lower()
    if tariff not in TARIFFS:
        errors.append(f"неизвестный тариф: {tariff or 'пусто'}")

    status = (row.get("status") or "").strip().lower()
    if status not in STATUSES:
        errors.append(f"неизвестный статус: {status or 'пусто'}")

    created = _dt(row, "created_at", errors, "создан", required=True)
    delivered = _dt(row, "delivered_at", errors, "доставлен", required=False)
    reschedule = _dt(row, "reschedule_to", errors, "перенос", required=False)

    if created and created > now:
        errors.append("время создания в будущем")
    if status == "delivered" and delivered is None and not any("доставлен" in e for e in errors):
        errors.append("статус «доставлен», но нет времени доставки")
    if status in ("in_transit", "cancelled") and delivered is not None:
        errors.append(f"статус «{status}», но указано время доставки")
    if created and delivered:
        if delivered < created:
            errors.append("доставка раньше создания")
        elif delivered - created > MAX_DELIVERY:
            errors.append("доставка позже создания более чем на 60 дней")
        if delivered > now:
            errors.append("время доставки в будущем")
    if created and reschedule and reschedule <= created:
        errors.append("перенос на время раньше создания")

    if errors:
        return None, errors
    return Order(order_no, channel, zone, tariff, created, status, delivered, reschedule), []
