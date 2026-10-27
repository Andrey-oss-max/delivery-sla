import csv
from pathlib import Path


def bar(value, total, width=20):
    """Текстовая полоса для консольного отчёта: доля value от total."""
    filled = 0 if not total else round(width * min(max(value, 0), total) / total)
    return "█" * filled + "·" * (width - filled)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
