from kit.report import write_csv
from kit.store import Store
from t05_orders_sla.core import aggregate, html_dashboard, load, run, text_report, validate

BASE = {"id": "1", "region": "Север", "created": "2026-10-01T08:00", "delivered": "2026-10-01T20:00",
        "promised_h": "24"}


def test_validate_computes_hours():
    rec, err = validate(dict(BASE))
    assert err is None and rec[-1] == 12.0


def test_validate_rejects_delivery_before_creation():
    _, err = validate(dict(BASE, delivered="2026-10-01T07:00"))
    assert err == "доставка раньше создания"


def test_validate_rejects_bad_date():
    assert validate(dict(BASE, created="вчера"))[1] == "неверный формат полей"


def test_sla_percentage_per_region():
    s = Store()
    rows = [dict(BASE, id="1"), dict(BASE, id="2", delivered="2026-10-05T08:00")]
    load(s, rows)
    (r,) = aggregate(s)
    assert (r["orders"], r["on_time"], r["sla_pct"]) == (2, 1, 50.0)


def test_reload_is_idempotent():
    s = Store()
    load(s, [dict(BASE)])
    load(s, [dict(BASE)])
    assert s.query("SELECT COUNT(*) AS n FROM orders")[0]["n"] == 1


def test_run_from_csv_and_reports(tmp_path):
    p = tmp_path / "o.csv"
    write_csv(p, [BASE, dict(BASE, id="2", delivered="2026-10-09T08:00")], list(BASE))
    agg, ok, bad = run(p)
    assert ok == 2 and bad == []
    assert "НИЖЕ ЦЕЛИ" in text_report(agg)
    assert "<table>" in html_dashboard(agg)
