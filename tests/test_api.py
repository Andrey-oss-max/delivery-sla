from datetime import date

from fastapi.testclient import TestClient

from sla import service
from sla.api import create_app
from sla.repository import InMemoryRepository
from sla.settings import Settings
from helpers import NOW, ZONES, row

SETTINGS = Settings(report_now=NOW.isoformat())


def make_client():
    repo = InMemoryRepository(ZONES.values(), holidays=[date(2026, 11, 4)])
    service.ingest([(2, row(order_no="A1")), (3, row(order_no="A2", delivered_at="2026-11-02 15:00"))], repo, NOW)
    service.recompute(repo, NOW)
    return TestClient(create_app(lambda: repo, SETTINGS)), repo


def test_summary():
    c, _ = make_client()
    body = c.get("/api/summary").json()
    assert (body["counted"], body["on_time"], body["sla_pct"], body["target"]) == (2, 1, 50.0, 95.0)


def test_filter_by_zone_and_period():
    c, _ = make_client()
    assert c.get("/api/summary?zone=OBL").json()["total"] == 0
    assert c.get("/api/daily?from=2026-11-02&to=2026-11-02").json()[0]["day"] == "2026-11-02"
    assert c.get("/api/summary?from=2026-11-03&to=2026-11-02").status_code == 422


def test_post_order_in_russian_values():
    c, repo = make_client()
    r = c.post("/api/orders", json={"order_no": "A3", "channel": "телефон", "zone": "OBL", "tariff": "стандарт",
                                    "created_at": "2026-11-05T09:00", "status": "в пути"})
    assert r.status_code == 201
    assert r.json()["deadline"] == "2026-11-10T21:00:00" and r.json()["outcome"] == "in_progress"
    assert len(repo.orders()) == 3


def test_post_invalid_order_gives_reason():
    c, _ = make_client()
    r = c.post("/api/orders", json={"order_no": "A4", "channel": "сайт", "zone": "CTR", "tariff": "экспресс",
                                    "created_at": "2026-11-05T09:00", "delivered_at": "2026-11-05T08:00",
                                    "status": "доставлен"})
    assert r.status_code == 422 and r.json()["detail"] == "доставка раньше создания"


def test_post_malformed_body_gives_422():
    c, _ = make_client()
    assert c.post("/api/orders", json={"order_no": "A5", "created_at": "вчера"}).status_code == 422


def test_late_and_by_zone():
    c, _ = make_client()
    assert c.get("/api/late").json()[0]["order_no"] == "A2"
    assert c.get("/api/by-zone").json()[0]["zone"] == "CTR"


def test_dashboard_page_and_static():
    c, _ = make_client()
    page = c.get("/")
    assert page.status_code == 200 and "SLA доставки" in page.text and "CTR — Центральный район" in page.text
    assert c.get("/static/chart.umd.min.js").status_code == 200
