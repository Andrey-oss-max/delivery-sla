"""Тема 5. Конвейер агрегации заказов и расчёта SLA доставки: отчёт и дашборд.

Цепочка: extract (CSV) -> validate -> load (SQLite через kit.Store) -> aggregate (SQL)
-> text_report / html_dashboard.
"""
from datetime import datetime

from kit.report import bar, read_csv
from kit.store import Store

SCHEMA = """CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY, region TEXT NOT NULL, created TEXT NOT NULL,
    delivered TEXT NOT NULL, promised_h REAL NOT NULL, hours REAL NOT NULL)"""


def validate(row):
    try:
        created = datetime.fromisoformat(row["created"])
        delivered = datetime.fromisoformat(row["delivered"])
        promised = float(row["promised_h"])
    except (KeyError, ValueError):
        return None, "неверный формат полей"
    if not row.get("region"):
        return None, "нет региона"
    if delivered < created:
        return None, "доставка раньше создания"
    if promised <= 0:
        return None, "срок должен быть положительным"
    hours = (delivered - created).total_seconds() / 3600
    return (row["id"], row["region"], row["created"], row["delivered"], promised, round(hours, 2)), None


def load(store, rows):
    store.execute(SCHEMA)
    good, bad = [], []
    for r in rows:
        rec, err = validate(r)
        if err:
            bad.append((r.get("id"), err))
        else:
            good.append(rec)
    store.insert_many("INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?)", good)
    return len(good), bad


def aggregate(store):
    return store.query(
        """SELECT region, COUNT(*) AS orders,
                  SUM(hours <= promised_h) AS on_time,
                  ROUND(100.0 * SUM(hours <= promised_h) / COUNT(*), 1) AS sla_pct,
                  ROUND(AVG(hours), 2) AS avg_h
           FROM orders GROUP BY region ORDER BY sla_pct""")


def run(csv_path, store=None):
    store = store or Store()
    ok, bad = load(store, read_csv(csv_path))
    return aggregate(store), ok, bad


def text_report(rows, target=95.0):
    out = []
    for r in rows:
        flag = "ОК" if r["sla_pct"] >= target else "НИЖЕ ЦЕЛИ"
        out.append("%-10s %s %5.1f%%  заказов: %s  %s"
                   % (r["region"], bar(r["sla_pct"], 100), r["sla_pct"], r["orders"], flag))
    return "\n".join(out)


def html_dashboard(rows, target=95.0):
    cells = "".join(
        "<tr class='%s'><td>%s</td><td>%s</td><td>%s%%</td><td>%s</td></tr>"
        % ("ok" if r["sla_pct"] >= target else "bad", r["region"], r["orders"], r["sla_pct"], r["avg_h"])
        for r in rows)
    return ("<!doctype html><meta charset='utf-8'><title>SLA доставки</title>"
            "<style>.bad{background:#fdd}.ok{background:#dfd}td,th{padding:4px 10px}</style>"
            "<h1>SLA доставки</h1><table><tr><th>Регион</th><th>Заказов</th><th>SLA</th><th>Среднее, ч</th></tr>"
            "%s</table>" % cells)
