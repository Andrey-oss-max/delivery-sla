"""Уровень 3: настоящая MySQL. Пропускаются, если не задано RUN_DB_TESTS=1.
Каждый тест работает в отдельной базе sla_test, которая создаётся заново."""
import os
from datetime import date, datetime
from pathlib import Path

import pytest

from sla import service
from sla.domain import Zone
from sla.repository import MysqlRepository, connect_mysql
from sla.settings import Settings
from helpers import NOW, row

pytestmark = pytest.mark.skipif(not os.getenv("RUN_DB_TESTS"), reason="нужна база: RUN_DB_TESTS=1")
SCHEMA = (Path(__file__).resolve().parent.parent / "db" / "init.sql").read_text(encoding="utf-8")


@pytest.fixture
def repo():
    base = Settings.from_env()
    admin = connect_mysql(base, attempts=10)
    with admin.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS sla_test")
        cur.execute("CREATE DATABASE sla_test CHARACTER SET utf8mb4")
    admin.close()
    conn = connect_mysql(Settings(**{**base.__dict__, "db_name": "sla_test"}))
    r = MysqlRepository(conn)
    r.apply_schema(SCHEMA)
    yield r
    conn.close()


def test_schema_is_idempotent_and_seeded(repo):
    repo.apply_schema(SCHEMA)
    assert sorted(repo.zones()) == ["CTR", "LEN", "MOS", "OBL", "PRG"]
    assert date(2026, 11, 4) in repo.holidays()


def test_zone_upsert_by_code(repo):
    added, updated = repo.upsert_zones([Zone("ZEL", "Зеленоградск", 8, 2), Zone("PRG", "Пригород (до 15 км)", 6, 2),
                                        Zone("CTR", "Центральный район", 3, 1)])
    assert (added, updated) == (1, 1)
    assert repo.zones()["PRG"].name == "Пригород (до 15 км)"


def test_ingest_recompute_and_reports(repo):
    rep = service.ingest([(2, row(order_no="A1")), (3, row(order_no="A2", delivered_at="2026-11-02 15:00")),
                          (4, row(order_no="A3", zone="ZZZ"))], repo, NOW, source="test")
    assert (rep.accepted, len(rep.rejected)) == (2, 1)
    service.recompute(repo, NOW)
    daily = repo.daily()
    assert daily[0]["zone"] == "CTR" and daily[0]["sla_pct"] == 50.0
    assert repo.late_orders()[0]["order_no"] == "A2"
    assert repo.rejected()[0]["reason"] == "неизвестная зона: ZZZ"


def test_reimport_does_not_duplicate(repo):
    service.ingest([(2, row(order_no="A1", status="in_transit", delivered_at=""))], repo, NOW)
    rep = service.ingest([(2, row(order_no="A1"))], repo, NOW)
    assert (rep.added, rep.updated) == (0, 1)
    orders = repo.orders()
    assert len(orders) == 1 and orders[0].delivered_at == datetime(2026, 11, 2, 12, 0)


def test_cyrillic_is_stored(repo):
    service.ingest([(7, row(order_no="A1", zone="ZZZ"))], repo, NOW, source="реестр_доставок.csv")
    assert "неизвестная зона" in repo.rejected()[0]["reason"]


def test_period_filter_in_sql(repo):
    later = row(order_no="B1", created_at="2026-11-05 09:00", delivered_at="2026-11-05 10:00")
    service.ingest([(2, row(order_no="A1")), (3, later)], repo, NOW)
    service.recompute(repo, NOW)
    assert [r.order_no for r in repo.results(date_from=date(2026, 11, 5))] == ["B1"]
    assert [r.order_no for r in repo.results(date_to=date(2026, 11, 2))] == ["A1"]
