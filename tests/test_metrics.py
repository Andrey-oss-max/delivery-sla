from datetime import datetime

import pytest
from hypothesis import given, strategies as st

from sla.domain import EXCLUDED, IN_PROGRESS, LATE, ON_TIME, OPEN_LATE, SlaResult
from sla.metrics import by_day_zone, by_zone, deadline, evaluate, percentile, summarize
from helpers import CAL, NOW, ZONES, order


def ev(**kw):
    o = order(**kw)
    return evaluate(o, ZONES[o.zone], CAL, NOW)


def test_express_on_time():
    r = ev()
    assert (r.outcome, r.hours, r.delay_h) == (ON_TIME, 2.0, None)


def test_delivered_exactly_at_deadline_is_on_time():
    assert ev(delivered_at=datetime(2026, 11, 2, 13, 0)).outcome == ON_TIME


def test_one_minute_after_deadline_is_late():
    r = ev(delivered_at=datetime(2026, 11, 2, 13, 1))
    assert (r.outcome, r.delay_h) == (LATE, 0.02)


def test_standard_uses_working_calendar():
    o = order(tariff="standard", created_at=datetime(2026, 11, 3, 15, 0), delivered_at=datetime(2026, 11, 6, 20, 30))
    assert deadline(o, ZONES["CTR"], CAL) == datetime(2026, 11, 6, 21, 0)
    assert evaluate(o, ZONES["CTR"], CAL, NOW).outcome == ON_TIME


def test_client_reschedule_moves_deadline():
    r = ev(reschedule_to=datetime(2026, 11, 3, 12, 0), delivered_at=datetime(2026, 11, 3, 11, 0))
    assert (r.deadline, r.outcome) == (datetime(2026, 11, 3, 12, 0), ON_TIME)


def test_cancelled_is_excluded():
    assert ev(status="cancelled", delivered_at=None).outcome == EXCLUDED


def test_in_transit_before_deadline_is_in_progress():
    r = ev(status="in_transit", delivered_at=None, created_at=datetime(2026, 11, 6, 16, 0))
    assert r.outcome == IN_PROGRESS


def test_in_transit_after_deadline_is_open_late():
    r = ev(status="in_transit", delivered_at=None, created_at=datetime(2026, 11, 6, 14, 0))
    assert (r.outcome, r.delay_h) == (OPEN_LATE, 1.0)


@pytest.mark.parametrize("p, expected", [(50, 3), (90, 5), (100, 5), (10, 1)])
def test_percentile_nearest_rank(p, expected):
    assert percentile([5, 1, 4, 2, 3], p) == expected


def test_percentile_empty_and_bad_p():
    assert percentile([], 90) is None
    with pytest.raises(ValueError):
        percentile([1], 0)


def _res(outcome, hours=None, delay=None, zone="CTR", day=2):
    return SlaResult("x", zone, datetime(2026, 11, day, 21, 0), outcome, hours, delay)


def test_summary_counts_and_percent():
    s = summarize([_res(ON_TIME, 2), _res(ON_TIME, 3), _res(LATE, 10, 4), _res(OPEN_LATE, None, 2),
                   _res(IN_PROGRESS), _res(EXCLUDED)])
    assert (s.total, s.counted, s.on_time) == (6, 4, 2)
    assert s.sla_pct == 50.0
    assert (s.p50_h, s.p90_h, s.avg_delay_h) == (3, 10, 3.0)


def test_summary_empty_period_has_no_percent():
    s = summarize([])
    assert s.total == 0 and s.sla_pct is None and s.p90_h is None


def test_summary_only_in_progress_has_no_percent():
    assert summarize([_res(IN_PROGRESS), _res(EXCLUDED)]).sla_pct is None


def test_all_on_time_is_100_and_all_late_is_0():
    assert summarize([_res(ON_TIME, 1)] * 3).sla_pct == 100.0
    assert summarize([_res(LATE, 9, 1)] * 3).sla_pct == 0.0


def test_grouping_by_day_and_zone():
    rows = [_res(ON_TIME, 1, zone="CTR", day=2), _res(LATE, 9, 1, zone="CTR", day=2),
            _res(ON_TIME, 1, zone="OBL", day=3)]
    g = by_day_zone(rows)
    assert list(g) == [(datetime(2026, 11, 2).date(), "CTR"), (datetime(2026, 11, 3).date(), "OBL")]
    assert g[(datetime(2026, 11, 2).date(), "CTR")].sla_pct == 50.0
    assert by_zone(rows)["OBL"].sla_pct == 100.0


outcomes = st.sampled_from([ON_TIME, LATE, OPEN_LATE, IN_PROGRESS, EXCLUDED])


@given(st.lists(outcomes, max_size=60))
def test_summary_invariants(items):
    s = summarize([_res(o, 1.0 if o in (ON_TIME, LATE) else None, 1.0 if o in (LATE, OPEN_LATE) else None)
                   for o in items])
    assert s.on_time + s.late + s.open_late + s.in_progress + s.excluded == s.total == len(items)
    assert s.sla_pct is None or 0.0 <= s.sla_pct <= 100.0


@given(st.lists(st.floats(min_value=0, max_value=500, allow_nan=False), min_size=1, max_size=50))
def test_p50_never_greater_than_p90(values):
    assert percentile(values, 50) <= percentile(values, 90) <= max(values)
