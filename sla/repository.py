"""Хранилище: интерфейс и две реализации - в памяти (для тестов) и MySQL (PyMySQL).
Драйвер импортируется только внутри connect_mysql, поэтому ядро и тесты без базы его не требуют."""
import logging
import time
from dataclasses import asdict
from datetime import date, datetime
from typing import Iterable, Optional, Protocol

from .domain import Order, RepositoryError, SlaResult, Zone
from .metrics import Summary

log = logging.getLogger(__name__)


class Repository(Protocol):
    def zones(self) -> dict: ...
    def upsert_zones(self, zones: Iterable[Zone]) -> tuple: ...
    def holidays(self) -> frozenset: ...
    def start_batch(self, source: str, kind: str) -> int: ...
    def finish_batch(self, batch_id: int, accepted: int, rejected: int) -> None: ...
    def upsert_orders(self, orders: Iterable[Order], batch_id: Optional[int]) -> tuple: ...
    def add_rejected(self, batch_id: Optional[int], items: Iterable[tuple]) -> None: ...
    def orders(self) -> list: ...
    def save_results(self, results: Iterable[SlaResult]) -> None: ...
    def save_daily(self, rows: dict) -> None: ...
    def results(self, date_from=None, date_to=None, zone=None) -> list: ...
    def daily(self, date_from=None, date_to=None, zone=None) -> list: ...
    def late_orders(self, limit=10, date_from=None, date_to=None, zone=None) -> list: ...
    def rejected(self, limit=20) -> list: ...


def _in_period(day: date, date_from, date_to) -> bool:
    return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)


def _daily_row(day, zone, s: Summary) -> dict:
    return {"day": day, "zone": zone, "total": s.total, "on_time": s.on_time, "late": s.late,
            "open_late": s.open_late, "in_progress": s.in_progress, "excluded": s.excluded,
            "sla_pct": s.sla_pct, "p50_h": s.p50_h, "p90_h": s.p90_h}


class InMemoryRepository:
    def __init__(self, zones: Iterable[Zone] = (), holidays: Iterable[date] = ()):
        self._zones = {z.code: z for z in zones}
        self._holidays = frozenset(holidays)
        self._orders = {}
        self._results = {}
        self._daily = {}
        self._rejected = []
        self._batches = []

    def zones(self):
        return dict(self._zones)

    def upsert_zones(self, zones):
        added = updated = 0
        for z in zones:
            if z.code in self._zones:
                updated += self._zones[z.code] != z
            else:
                added += 1
            self._zones[z.code] = z
        return added, updated

    def holidays(self):
        return self._holidays

    def start_batch(self, source, kind):
        self._batches.append({"source": source, "kind": kind, "accepted": None, "rejected": None})
        return len(self._batches)

    def finish_batch(self, batch_id, accepted, rejected):
        self._batches[batch_id - 1].update(accepted=accepted, rejected=rejected)

    def upsert_orders(self, orders, batch_id):
        added = updated = 0
        for o in orders:
            if o.zone not in self._zones:
                raise RepositoryError(f"нет зоны {o.zone}")
            if o.order_no in self._orders:
                updated += 1
            else:
                added += 1
            self._orders[o.order_no] = o
        return added, updated

    def add_rejected(self, batch_id, items):
        for line_no, order_no, raw, reason in items:
            self._rejected.append({"batch_id": batch_id, "line_no": line_no, "order_no": order_no,
                                   "raw": raw, "reason": reason})

    def orders(self):
        return list(self._orders.values())

    def save_results(self, results):
        self._results = {r.order_no: r for r in results}

    def save_daily(self, rows):
        self._daily = {k: _daily_row(k[0], k[1], s) for k, s in rows.items()}

    def results(self, date_from=None, date_to=None, zone=None):
        return [r for r in self._results.values()
                if _in_period(r.day, date_from, date_to) and (zone is None or r.zone == zone)]

    def daily(self, date_from=None, date_to=None, zone=None):
        return [row for k, row in sorted(self._daily.items())
                if _in_period(k[0], date_from, date_to) and (zone is None or k[1] == zone)]

    def late_orders(self, limit=10, date_from=None, date_to=None, zone=None):
        late = [r for r in self.results(date_from, date_to, zone) if r.delay_h is not None]
        late.sort(key=lambda r: (-r.delay_h, r.order_no))
        return [{**asdict(r), "tariff": self._orders[r.order_no].tariff,
                 "channel": self._orders[r.order_no].channel} for r in late[:limit]]

    def rejected(self, limit=20):
        return list(reversed(self._rejected))[:limit]


# ---------------------------------------------------------------- MySQL

def connect_mysql(settings, attempts=30, pause=2.0, sleep=time.sleep):
    """Подключение с повторами: MySQL в контейнере открывает порт раньше, чем готов принимать вход."""
    import pymysql  # драйвер нужен только здесь

    last = None
    for attempt in range(1, attempts + 1):
        try:
            conn = pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user,
                                   password=settings.db_password, database=settings.db_name,
                                   charset="utf8mb4", autocommit=False,
                                   cursorclass=pymysql.cursors.DictCursor)
            log.info("подключено к MySQL %s:%s/%s (попытка %d)", settings.db_host, settings.db_port,
                     settings.db_name, attempt)
            return conn
        except pymysql.err.OperationalError as exc:
            last = exc
            log.warning("MySQL недоступен (попытка %d из %d): %s", attempt, attempts, exc.args[-1])
            if attempt < attempts:
                sleep(pause)
    raise RepositoryError(f"не удалось подключиться к MySQL: {last}")


def split_sql(script: str) -> list:
    """Делит SQL-скрипт на команды по ';' в конце строки, пропуская комментарии."""
    statements, buf = [], []
    for line in script.splitlines():
        if line.strip().startswith("--") or not line.strip():
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            statements.append("\n".join(buf).rstrip().rstrip(";"))
            buf = []
    if buf:
        statements.append("\n".join(buf))
    return statements


def _filters(date_from, date_to, zone, day_col="r.deadline", zone_col="z.code"):
    where, params = [], []
    if date_from is not None:
        where.append(f"DATE({day_col}) >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append(f"DATE({day_col}) <= %s")
        params.append(date_to)
    if zone is not None:
        where.append(f"{zone_col} = %s")
        params.append(zone)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def _num(v):
    return None if v is None else float(v)


class MysqlRepository:
    """Соединение приходит снаружи: репозиторий его не открывает и не закрывает."""

    def __init__(self, conn):
        self.conn = conn

    def _run(self, fn):
        try:
            with self.conn.cursor() as cur:
                out = fn(cur)
            self.conn.commit()
            return out
        except RepositoryError:
            self.conn.rollback()
            raise
        except Exception as exc:  # ошибки драйвера заворачиваются в свою
            self.conn.rollback()
            if type(exc).__module__.startswith("pymysql"):
                raise RepositoryError(str(exc)) from exc
            raise

    def apply_schema(self, script: str) -> int:
        statements = split_sql(script)

        def go(cur):
            for st in statements:
                cur.execute(st)
            return len(statements)
        return self._run(go)

    def zones(self):
        def go(cur):
            cur.execute("SELECT code, name, express_hours, standard_days FROM zone ORDER BY code")
            return {r["code"]: Zone(**r) for r in cur.fetchall()}
        return self._run(go)

    def upsert_zones(self, zones):
        def go(cur):
            cur.execute("SELECT code, name, express_hours, standard_days FROM zone")
            old = {r["code"]: Zone(**r) for r in cur.fetchall()}
            added = updated = 0
            for z in zones:
                if old.get(z.code) == z:
                    continue
                cur.execute(
                    "INSERT INTO zone (code, name, express_hours, standard_days) VALUES (%s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE name = VALUES(name), express_hours = VALUES(express_hours), "
                    "standard_days = VALUES(standard_days)",
                    (z.code, z.name, z.express_hours, z.standard_days))
                added += z.code not in old
                updated += z.code in old
            return added, updated
        return self._run(go)

    def holidays(self):
        def go(cur):
            cur.execute("SELECT day FROM holiday")
            return frozenset(r["day"] for r in cur.fetchall())
        return self._run(go)

    def start_batch(self, source, kind):
        def go(cur):
            cur.execute("INSERT INTO import_batch (source, kind) VALUES (%s, %s)", (source[:255], kind))
            return cur.lastrowid
        return self._run(go)

    def finish_batch(self, batch_id, accepted, rejected):
        self._run(lambda cur: cur.execute(
            "UPDATE import_batch SET accepted = %s, rejected = %s WHERE id = %s", (accepted, rejected, batch_id)))

    def upsert_orders(self, orders, batch_id):
        orders = list(orders)

        def go(cur):
            cur.execute("SELECT code, id FROM zone")
            zone_id = {r["code"]: r["id"] for r in cur.fetchall()}
            existing = set()
            if orders:
                cur.execute("SELECT order_no FROM orders WHERE order_no IN (" + ", ".join(["%s"] * len(orders)) + ")",
                            [o.order_no for o in orders])
                existing = {r["order_no"] for r in cur.fetchall()}
            added = updated = 0
            for o in orders:
                if o.zone not in zone_id:
                    raise RepositoryError(f"нет зоны {o.zone}")
                cur.execute(
                    "INSERT INTO orders (order_no, channel, zone_id, tariff, created_at, delivered_at, status, "
                    "reschedule_to, batch_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE channel = VALUES(channel), zone_id = VALUES(zone_id), "
                    "tariff = VALUES(tariff), created_at = VALUES(created_at), delivered_at = VALUES(delivered_at), "
                    "status = VALUES(status), reschedule_to = VALUES(reschedule_to), batch_id = VALUES(batch_id)",
                    (o.order_no, o.channel, zone_id[o.zone], o.tariff, o.created_at, o.delivered_at, o.status,
                     o.reschedule_to, batch_id))
                added += o.order_no not in existing
                updated += o.order_no in existing
            return added, updated
        return self._run(go)

    def add_rejected(self, batch_id, items):
        rows = [(batch_id, line_no, (order_no or "")[:64], raw[:1000], reason[:500])
                for line_no, order_no, raw, reason in items]
        if rows:
            self._run(lambda cur: cur.executemany(
                "INSERT INTO rejected (batch_id, line_no, order_no, raw, reason) VALUES (%s, %s, %s, %s, %s)", rows))

    def orders(self):
        def go(cur):
            cur.execute("SELECT o.order_no, o.channel, z.code AS zone, o.tariff, o.created_at, o.status, "
                        "o.delivered_at, o.reschedule_to FROM orders o JOIN zone z ON z.id = o.zone_id ORDER BY o.id")
            return [Order(**r) for r in cur.fetchall()]
        return self._run(go)

    def save_results(self, results):
        rows = [(r.order_no, r.deadline, r.outcome, r.hours, r.delay_h) for r in results]

        def go(cur):
            cur.execute("DELETE FROM sla_result")
            cur.executemany(
                "INSERT INTO sla_result (order_id, deadline, outcome, hours, delay_h) "
                "SELECT id, %s, %s, %s, %s FROM orders WHERE order_no = %s",
                [(d, o, h, dl, no) for no, d, o, h, dl in rows])
        self._run(go)

    def save_daily(self, rows):
        def go(cur):
            cur.execute("SELECT code, id FROM zone")
            zone_id = {r["code"]: r["id"] for r in cur.fetchall()}
            cur.execute("DELETE FROM sla_daily")
            cur.executemany(
                "INSERT INTO sla_daily (day, zone_id, total, on_time, late, open_late, in_progress, excluded, "
                "sla_pct, p50_h, p90_h) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [(day, zone_id[zone], s.total, s.on_time, s.late, s.open_late, s.in_progress, s.excluded,
                  s.sla_pct, s.p50_h, s.p90_h) for (day, zone), s in rows.items()])
        self._run(go)

    def results(self, date_from=None, date_to=None, zone=None):
        where, params = _filters(date_from, date_to, zone)

        def go(cur):
            cur.execute("SELECT o.order_no, z.code AS zone, r.deadline, r.outcome, r.hours, r.delay_h "
                        "FROM sla_result r JOIN orders o ON o.id = r.order_id JOIN zone z ON z.id = o.zone_id"
                        + where + " ORDER BY r.deadline, o.order_no", params)
            return [SlaResult(r["order_no"], r["zone"], r["deadline"], r["outcome"], _num(r["hours"]),
                              _num(r["delay_h"])) for r in cur.fetchall()]
        return self._run(go)

    def daily(self, date_from=None, date_to=None, zone=None):
        where, params = _filters(date_from, date_to, zone, day_col="d.day")

        def go(cur):
            cur.execute("SELECT d.day, z.code AS zone, d.total, d.on_time, d.late, d.open_late, d.in_progress, "
                        "d.excluded, d.sla_pct, d.p50_h, d.p90_h FROM sla_daily d JOIN zone z ON z.id = d.zone_id"
                        + where + " ORDER BY d.day, z.code", params)
            return [{**r, "sla_pct": _num(r["sla_pct"]), "p50_h": _num(r["p50_h"]), "p90_h": _num(r["p90_h"])}
                    for r in cur.fetchall()]
        return self._run(go)

    def late_orders(self, limit=10, date_from=None, date_to=None, zone=None):
        where, params = _filters(date_from, date_to, zone)
        where = (where + " AND " if where else " WHERE ") + "r.delay_h IS NOT NULL"

        def go(cur):
            cur.execute("SELECT o.order_no, z.code AS zone, r.deadline, r.outcome, r.hours, r.delay_h, o.tariff, "
                        "o.channel FROM sla_result r JOIN orders o ON o.id = r.order_id JOIN zone z ON z.id = o.zone_id"
                        + where + " ORDER BY r.delay_h DESC, o.order_no LIMIT %s", params + [limit])
            return [{**r, "hours": _num(r["hours"]), "delay_h": _num(r["delay_h"])} for r in cur.fetchall()]
        return self._run(go)

    def rejected(self, limit=20):
        def go(cur):
            cur.execute("SELECT batch_id, line_no, order_no, raw, reason FROM rejected ORDER BY id DESC LIMIT %s",
                        (limit,))
            return cur.fetchall()
        return self._run(go)


def as_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value))
