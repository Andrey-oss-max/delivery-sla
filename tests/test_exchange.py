import pytest

from sla.exchange import FormatError, parse_orders, parse_zones, report_csv
from sla.domain import Zone

HEAD = "Номер;Канал;Зона;Тариф;Создан;Доставлен;Статус;Перенос\n"


def test_orders_russian_values_are_mapped_to_codes():
    rows = parse_orders("﻿" + HEAD + "D-1;сайт;CTR;экспресс;2026-11-02 10:00;2026-11-02 12:00;Доставлен;\n")
    assert rows == [(2, {"order_no": "D-1", "channel": "site", "zone": "CTR", "tariff": "express",
                         "created_at": "2026-11-02 10:00", "delivered_at": "2026-11-02 12:00",
                         "status": "delivered", "reschedule_to": ""})]


def test_empty_lines_are_skipped_and_line_numbers_kept():
    rows = parse_orders(HEAD + ";;;;;;;\n" + "D-2;телефон;OBL;стандарт;2026-11-02 10:00;;в пути;\n")
    assert [n for n, _ in rows] == [3]
    assert rows[0][1]["status"] == "in_transit"


def test_missing_columns():
    with pytest.raises(FormatError, match="Зона"):
        parse_orders("Номер;Создан;Статус\nD-1;2026-11-02 10:00;доставлен\n")


def test_empty_file():
    with pytest.raises(FormatError):
        parse_orders("")


def test_zones_with_errors():
    text = ("Код;Наименование;Экспресс_ч;Стандарт_дн\nctr;Центр;3;1\nCTR;Повтор;3;1\n"
            "SVT;Светлогорск;восемь;2\nFAR;Далеко;100;2\n")
    zones, errors = parse_zones(text)
    assert zones == [Zone("CTR", "Центр", 3, 1)]
    assert errors == [(3, "повтор кода CTR"), (4, "срок не целое число"),
                      (5, "срок вне допустимых границ (1-72 ч, 1-10 дн)")]


def test_report_csv_format():
    text = report_csv([{"day": "2026-11-02", "zone": "CTR", "total": 3, "on_time": 2, "late": 1, "open_late": 0,
                        "in_progress": 0, "excluded": 0, "sla_pct": 66.7, "p50_h": 2.0, "p90_h": None}])
    head, line = text.splitlines()
    assert head.startswith("Дата;Зона;Заказов")
    assert line == "2026-11-02;CTR;3;2;1;0;0;0;66.7;2.0;"
