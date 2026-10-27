"""Командная строка конвейера: python -m sla.cli <команда>. Единственное место сборки для CLI."""
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from . import exchange, service
from .carrier_client import CarrierClient, CarrierError
from .domain import RepositoryError
from .metrics import by_zone, summarize
from .repository import MysqlRepository, connect_mysql
from .settings import Settings
from .simulate import generate

log = logging.getLogger("sla")
ROOT = Path(__file__).resolve().parent.parent


def bar(pct, width=20):
    if pct is None:
        return " " * width
    filled = round(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def _f(v, digits=1):
    return "-" if v is None else f"{v:.{digits}f}"


def print_report(repo, target, date_from=None, date_to=None, zone=None, out=sys.stdout):
    results = repo.results(date_from, date_to, zone)
    total = summarize(results)
    names = {z.code: z.name for z in repo.zones().values()}
    period = f"{date_from or 'начало'} - {date_to or 'конец'}"
    print(f"SLA доставки за период {period}, цель {target:.0f}%", file=out)
    print(f"заказов: {total.total}  учтено в SLA: {total.counted}  вовремя: {total.on_time}  "
          f"просрочено: {total.late}  просрочено в пути: {total.open_late}  в работе: {total.in_progress}  "
          f"отменено: {total.excluded}", file=out)
    print(f"SLA: {_f(total.sla_pct)}%   P50: {_f(total.p50_h)} ч   P90: {_f(total.p90_h)} ч   "
          f"средняя просрочка: {_f(total.avg_delay_h)} ч", file=out)
    print("", file=out)
    print(f"{'зона':<5}{'наименование':<25}{'учтено':>7}{'вовремя':>9}  {'SLA, %':>6}  {'':20}  {'P90, ч':>6}  оценка",
          file=out)
    for code, s in by_zone(results).items():
        mark = "-" if s.sla_pct is None else ("в норме" if s.sla_pct >= target else "НИЖЕ ЦЕЛИ")
        print(f"{code:<5}{names.get(code, code)[:24]:<25}{s.counted:>7}{s.on_time:>9}  {_f(s.sla_pct):>6}  "
              f"{bar(s.sla_pct)}  {_f(s.p90_h):>6}  {mark}", file=out)
    late = repo.late_orders(5, date_from, date_to, zone)
    if late:
        print("", file=out)
        print("наибольшие просрочки:", file=out)
        for r in late:
            state = "в пути" if r["outcome"] == "open_late" else "доставлен"
            print(f"  {r['order_no']:<15}{r['zone']:<5}{r['tariff']:<10}срок {r['deadline']:%d.%m %H:%M}  "
                  f"просрочка {r['delay_h']:>5.1f} ч  ({state})", file=out)
    return total


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    p = argparse.ArgumentParser(prog="sla", description="Конвейер агрегации заказов и расчёта SLA доставки")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="применить схему db/init.sql")
    z = sub.add_parser("zones", help="загрузить справочник зон")
    z.add_argument("file")
    im = sub.add_parser("import", help="загрузить реестр доставок из файла или по HTTP")
    im.add_argument("file", nargs="?")
    im.add_argument("--url", help="имя файла у службы доставки, например reestr_dostavok.csv")
    sm = sub.add_parser("simulate", help="сгенерировать поток заказов со сбоями")
    sm.add_argument("--count", type=int, default=200)
    sm.add_argument("--days", type=int, default=14)
    sm.add_argument("--seed", type=int, default=42)
    sub.add_parser("recompute", help="пересчитать SLA и сводку по дням и зонам")
    for name in ("report", "export"):
        c = sub.add_parser(name, help="отчёт в консоль" if name == "report" else "выгрузить отчёт SLA в CSV")
        if name == "export":
            c.add_argument("file")
        c.add_argument("--from", dest="date_from", type=date.fromisoformat)
        c.add_argument("--to", dest="date_to", type=date.fromisoformat)
        c.add_argument("--zone")
    rj = sub.add_parser("rejected", help="последние отклонённые строки")
    rj.add_argument("--limit", type=int, default=10)
    pl = sub.add_parser("pipeline", help="весь конвейер: схема, справочник, реестр, пересчёт, отчёт")
    pl.add_argument("--zones", default="exchange/zones.csv")
    pl.add_argument("--orders", default="exchange/reestr_dostavok.csv")
    args = p.parse_args(argv)

    settings = Settings.from_env()
    now = settings.now()
    try:
        conn = connect_mysql(settings)
    except RepositoryError as exc:
        log.error("%s", exc)
        return 2
    repo = MysqlRepository(conn)
    try:
        return run(args, repo, settings, now)
    except (RepositoryError, CarrierError, exchange.FormatError, OSError) as exc:
        log.error("%s", exc)
        return 1
    finally:
        conn.close()


def run(args, repo, settings, now):
    if args.cmd in ("init", "pipeline"):
        n = repo.apply_schema((ROOT / "db" / "init.sql").read_text(encoding="utf-8"))
        log.info("схема применена: %d команд", n)
    if args.cmd == "zones" or args.cmd == "pipeline":
        path = args.file if args.cmd == "zones" else args.zones
        zones, errors = exchange.parse_zones(exchange.read_text(path))
        added, updated = repo.upsert_zones(zones)
        log.info("справочник зон: добавлено %d, обновлено %d, отклонено %d", added, updated, len(errors))
        for line_no, reason in errors:
            log.warning("строка %d: %s", line_no, reason)
    if args.cmd == "import" or args.cmd == "pipeline":
        if args.cmd == "import" and args.url:
            text = CarrierClient(settings.carrier_url).registry(args.url)
            source = f"{settings.carrier_url}/{args.url}"
        else:
            source = args.file if args.cmd == "import" else args.orders
            if not source:
                log.error("укажите файл или --url")
                return 2
            text = exchange.read_text(source)
        rep = service.ingest(exchange.parse_orders(text), repo, now, source=source, kind="registry")
        print(f"принято: {rep.accepted} (новых {rep.added}, обновлено {rep.updated}), отклонено: {len(rep.rejected)}")
    if args.cmd == "simulate":
        rows = generate(repo.zones(), args.count, now, args.days, args.seed)
        rep = service.ingest(rows, repo, now, source=f"simulate seed={args.seed}", kind="simulate")
        print(f"сгенерировано: {len(rows)}, принято: {rep.accepted}, отклонено: {len(rep.rejected)}")
    if args.cmd in ("recompute", "pipeline", "import", "simulate"):
        service.recompute(repo, now)
    if args.cmd in ("report", "pipeline"):
        kw = {} if args.cmd == "pipeline" else dict(date_from=args.date_from, date_to=args.date_to, zone=args.zone)
        print()
        print_report(repo, settings.sla_target, **kw)
    if args.cmd == "export":
        rows = repo.daily(args.date_from, args.date_to, args.zone)
        exchange.write_text(args.file, exchange.report_csv(rows))
        print(f"выгружено строк: {len(rows)} -> {args.file}")
    if args.cmd == "rejected":
        for r in repo.rejected(args.limit):
            print(f"пакет {r['batch_id']:<3} строка {r['line_no']:<4} {r['order_no'] or '-':<15} {r['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
