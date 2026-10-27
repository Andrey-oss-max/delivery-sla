from datetime import datetime

import pytest

from sla.rules import parse_dt, validate_row
from helpers import NOW, ZONES, row


def errors(**kw):
    return validate_row(row(**kw), ZONES, NOW)[1]


def test_correct_row_gives_order():
    order, errs = validate_row(row(), ZONES, NOW)
    assert errs == []
    assert order.order_no == "D-1" and order.delivered_at == datetime(2026, 11, 2, 12, 0)


def test_codes_are_normalized():
    order, _ = validate_row(row(zone=" ctr ", tariff="EXPRESS", channel="Site"), ZONES, NOW)
    assert (order.zone, order.tariff, order.channel) == ("CTR", "express", "site")


def test_delivery_before_creation_rejected():
    assert errors(delivered_at="2026-11-02 09:59") == ["доставка раньше создания"]


def test_delivery_at_creation_moment_is_allowed():
    assert errors(delivered_at="2026-11-02 10:00") == []


def test_unknown_zone():
    assert errors(zone="ZZZ") == ["неизвестная зона: ZZZ"]


def test_missing_zone():
    assert errors(zone="") == ["нет зоны доставки"]


@pytest.mark.parametrize("field, value, message", [
    ("tariff", "turbo", "неизвестный тариф: turbo"),
    ("channel", "", "неизвестный канал: пусто"),
    ("status", "lost", "неизвестный статус: lost"),
    ("order_no", "", "нет номера заказа"),
    ("order_no", "D 1;DROP", "недопустимый номер заказа: D 1;DROP"),
])
def test_reference_fields(field, value, message):
    assert errors(**{field: value}) == [message]


def test_bad_date_format():
    assert errors(created_at="2026/11/02 10:00?") == ["неверный формат времени «создан»: 2026/11/02 10:00?"]


def test_created_in_future():
    assert errors(created_at="2026-11-06 18:01", delivered_at="", status="in_transit") == ["время создания в будущем"]


def test_created_exactly_now_is_allowed():
    assert errors(created_at="2026-11-06 18:00", delivered_at="", status="in_transit") == []


def test_delivered_status_requires_time():
    assert errors(delivered_at="") == ["статус «доставлен», но нет времени доставки"]


def test_in_transit_must_not_have_delivery_time():
    assert errors(status="in_transit") == ["статус «in_transit», но указано время доставки"]


def test_too_long_delivery():
    assert errors(created_at="2026-08-01 10:00", delivered_at="2026-10-01 10:01") == [
        "доставка позже создания более чем на 60 дней"]


def test_reschedule_before_creation():
    assert errors(reschedule_to="2026-11-02 09:00") == ["перенос на время раньше создания"]


def test_several_errors_are_collected():
    assert len(errors(zone="", tariff="x", status="y")) == 3


@pytest.mark.parametrize("text, expected", [
    ("2026-11-02 10:00", datetime(2026, 11, 2, 10, 0)),
    ("02.11.2026 10:00", datetime(2026, 11, 2, 10, 0)),
    ("2026-11-02T10:00:30", datetime(2026, 11, 2, 10, 0, 30)),
    ("2026-11-02T10:00+03:00", datetime(2026, 11, 2, 9, 0)),   # Москва -> Калининград
    ("2026-11-02T08:00Z", datetime(2026, 11, 2, 10, 0)),
])
def test_parse_dt_formats(text, expected):
    assert parse_dt(text) == expected
