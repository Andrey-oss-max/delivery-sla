from datetime import date, datetime

from sla.calendar import WorkCalendar
from helpers import CAL


def test_weekend_and_holiday_are_not_working():
    assert not CAL.is_working(date(2026, 11, 7))   # суббота
    assert not CAL.is_working(date(2026, 11, 4))   # День народного единства
    assert CAL.is_working(date(2026, 11, 5))


def test_order_before_cutoff_starts_same_day():
    assert CAL.start_day(datetime(2026, 11, 2, 13, 59)) == date(2026, 11, 2)


def test_order_at_cutoff_starts_next_working_day():
    assert CAL.start_day(datetime(2026, 11, 2, 14, 0)) == date(2026, 11, 3)


def test_order_after_cutoff_skips_holiday():
    # вторник после отсечки -> среда праздник -> в работу в четверг
    assert CAL.start_day(datetime(2026, 11, 3, 15, 0)) == date(2026, 11, 5)


def test_weekend_order_starts_monday():
    assert CAL.start_day(datetime(2026, 11, 7, 9, 0)) == date(2026, 11, 9)


def test_standard_deadline_one_day():
    assert CAL.standard_deadline(datetime(2026, 11, 2, 10, 0), 1) == datetime(2026, 11, 3, 21, 0)


def test_standard_deadline_over_holiday_and_weekend():
    # пятница 30.10 до отсечки, 3 рабочих дня: 02.11, 03.11, (04.11 праздник) 05.11
    assert CAL.standard_deadline(datetime(2026, 10, 30, 12, 0), 3) == datetime(2026, 11, 5, 21, 0)


def test_without_holidays_deadline_is_earlier():
    plain = WorkCalendar()
    assert plain.standard_deadline(datetime(2026, 11, 3, 15, 0), 1) == datetime(2026, 11, 5, 21, 0)
    assert CAL.standard_deadline(datetime(2026, 11, 3, 15, 0), 1) == datetime(2026, 11, 6, 21, 0)


def test_express_deadline_crosses_midnight():
    assert CAL.express_deadline(datetime(2026, 11, 2, 22, 30), 3) == datetime(2026, 11, 3, 1, 30)
