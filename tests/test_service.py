from datetime import date

from sla import service
from sla.domain import LATE, ON_TIME
from sla.repository import InMemoryRepository
from helpers import NOW, ZONES, row


def repo():
    return InMemoryRepository(ZONES.values(), holidays=[date(2026, 11, 4)])


def test_ingest_splits_good_and_bad_rows():
    r = repo()
    rep = service.ingest([(2, row(order_no="A1")), (3, row(order_no="A2", zone="ZZZ"))], r, NOW, source="t")
    assert (rep.accepted, rep.added, len(rep.rejected)) == (1, 1, 1)
    assert r.rejected()[0]["reason"] == "неизвестная зона: ZZZ"
    assert r.rejected()[0]["line_no"] == 3


def test_duplicate_in_one_batch_is_rejected():
    rep = service.ingest([(2, row(order_no="A1")), (3, row(order_no="A1"))], repo(), NOW)
    assert rep.accepted == 1
    assert rep.rejected[0][3] == "повтор номера заказа A1 (впервые в строке 2)"


def test_reimport_updates_instead_of_duplicating():
    r = repo()
    service.ingest([(2, row(order_no="A1", status="in_transit", delivered_at=""))], r, NOW)
    rep = service.ingest([(2, row(order_no="A1"))], r, NOW)
    assert (rep.added, rep.updated) == (0, 1)
    assert len(r.orders()) == 1 and r.orders()[0].status == "delivered"


def test_recompute_builds_results_and_daily_summary():
    r = repo()
    service.ingest([(2, row(order_no="A1")),
                    (3, row(order_no="A2", delivered_at="2026-11-02 13:30")),
                    (4, row(order_no="A3", zone="OBL", tariff="standard", created_at="2026-10-30 12:00",
                            delivered_at="2026-11-05 20:00"))], r, NOW)
    daily = service.recompute(r, NOW)
    outcomes = {x.order_no: x.outcome for x in r.results()}
    assert outcomes == {"A1": ON_TIME, "A2": LATE, "A3": ON_TIME}
    assert daily[(date(2026, 11, 2), "CTR")].sla_pct == 50.0
    assert r.daily(zone="OBL")[0]["day"] == date(2026, 11, 5)


def test_custom_rule_can_be_injected():
    def strict(row_, zones, now):
        return None, ["правило отключено"]
    rep = service.ingest([(2, row())], repo(), NOW, validate=strict)
    assert rep.accepted == 0 and rep.rejected[0][3] == "правило отключено"


def test_late_orders_sorted_by_delay():
    r = repo()
    service.ingest([(2, row(order_no="A1", delivered_at="2026-11-02 14:00")),
                    (3, row(order_no="A2", delivered_at="2026-11-02 18:00"))], r, NOW)
    service.recompute(r, NOW)
    assert [x["order_no"] for x in r.late_orders()] == ["A2", "A1"]
