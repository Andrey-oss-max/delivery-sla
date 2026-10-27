"""Обмен файлами с учётной системой службы доставки: справочник зон и реестр доставок на входе,
отчёт SLA на выходе. CSV, разделитель ';', UTF-8 (BOM допускается), первая строка - заголовки."""
import csv
import io
from pathlib import Path

from .domain import Zone

ORDER_COLUMNS = {  # заголовок в файле -> поле строки
    "Номер": "order_no", "Канал": "channel", "Зона": "zone", "Тариф": "tariff", "Создан": "created_at",
    "Доставлен": "delivered_at", "Статус": "status", "Перенос": "reschedule_to",
}
ZONE_COLUMNS = ("Код", "Наименование", "Экспресс_ч", "Стандарт_дн")
REPORT_COLUMNS = ("Дата", "Зона", "Заказов", "Вовремя", "Просрочено", "Просрочено_в_пути", "В_работе",
                  "Отменено", "SLA_%", "P50_ч", "P90_ч")

# значения учётной системы -> коды проекта (коды тоже принимаются как есть)
VALUES = {
    "channel": {"сайт": "site", "маркетплейс": "marketplace", "телефон": "phone"},
    "tariff": {"экспресс": "express", "стандарт": "standard"},
    "status": {"доставлен": "delivered", "в пути": "in_transit", "отменён": "cancelled", "отменен": "cancelled"},
}


class FormatError(Exception):
    pass


def _reader(text: str):
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None:
        raise FormatError("файл пуст")
    reader.fieldnames = [h.strip() for h in reader.fieldnames]
    return reader


def parse_orders(text: str):
    """Строки реестра доставок -> список (номер строки файла, словарь полей). Пустые строки пропускаются."""
    reader = _reader(text)
    missing = [h for h in ("Номер", "Зона", "Создан", "Статус") if h not in reader.fieldnames]
    if missing:
        raise FormatError("нет колонок: " + ", ".join(missing))
    rows = []
    for row in reader:
        if not any((v or "").strip() for k, v in row.items() if k is not None):
            continue
        rec = {}
        for head, key in ORDER_COLUMNS.items():
            value = (row.get(head) or "").strip()
            rec[key] = VALUES.get(key, {}).get(value.lower(), value)
        rows.append((reader.line_num, rec))
    return rows


def parse_zones(text: str):
    """Справочник зон -> (список Zone, список (номер строки, причина))."""
    reader = _reader(text)
    missing = [h for h in ZONE_COLUMNS if h not in reader.fieldnames]
    if missing:
        raise FormatError("нет колонок: " + ", ".join(missing))
    zones, errors, seen = [], [], set()
    for row in reader:
        code = (row["Код"] or "").strip().upper()
        name = (row["Наименование"] or "").strip()
        if not code and not name:
            continue
        try:
            express, standard = int(row["Экспресс_ч"]), int(row["Стандарт_дн"])
        except (TypeError, ValueError):
            errors.append((reader.line_num, "срок не целое число"))
            continue
        if not code or not name:
            errors.append((reader.line_num, "нет кода или наименования"))
        elif code in seen:
            errors.append((reader.line_num, f"повтор кода {code}"))
        elif not (1 <= express <= 72) or not (1 <= standard <= 10):
            errors.append((reader.line_num, "срок вне допустимых границ (1-72 ч, 1-10 дн)"))
        else:
            seen.add(code)
            zones.append(Zone(code, name, express, standard))
    return zones, errors


def _fmt(v):
    if v is None:
        return ""
    return f"{v:.1f}" if isinstance(v, float) else str(v)


def report_csv(daily_rows) -> str:
    """Строки сводки (как возвращает repo.daily) -> текст CSV для учётной системы."""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow(REPORT_COLUMNS)
    for r in daily_rows:
        w.writerow([r["day"], r["zone"], r["total"], r["on_time"], r["late"], r["open_late"], r["in_progress"],
                    r["excluded"], _fmt(r["sla_pct"]), _fmt(r["p50_h"]), _fmt(r["p90_h"])])
    return out.getvalue()


def read_text(path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def write_text(path, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8-sig")
