import tempfile
from pathlib import Path

from kit.report import write_csv

from .core import html_dashboard, run, text_report

ROWS = [
    {"id": "1", "region": "Север", "created": "2026-10-01T08:00", "delivered": "2026-10-01T20:00", "promised_h": "24"},
    {"id": "2", "region": "Север", "created": "2026-10-01T08:00", "delivered": "2026-10-03T08:00", "promised_h": "24"},
    {"id": "3", "region": "Юг", "created": "2026-10-01T09:00", "delivered": "2026-10-01T15:00", "promised_h": "12"},
    {"id": "4", "region": "Юг", "created": "2026-10-02T09:00", "delivered": "2026-10-01T09:00", "promised_h": "12"},
]


def main():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "orders.csv"
        write_csv(path, ROWS, ["id", "region", "created", "delivered", "promised_h"])
        agg, ok, bad = run(path)
        print(text_report(agg))
        print("принято: %s, отклонено: %s" % (ok, bad))
        (Path(d) / "dash.html").write_text(html_dashboard(agg), encoding="utf-8")
        print("дашборд: %s байт HTML" % (Path(d) / "dash.html").stat().st_size)


if __name__ == "__main__":
    main()
