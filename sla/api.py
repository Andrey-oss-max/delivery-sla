"""HTTP API и страница дашборда на FastAPI. Хранилище приходит зависимостью get_repo."""
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import service
from .exchange import VALUES
from .metrics import by_day, by_zone, summarize
from .settings import Settings

HERE = Path(__file__).resolve().parent


class OrderIn(BaseModel):
    order_no: str = Field(examples=["D-261026-90001"])
    channel: str = Field(examples=["сайт"])
    zone: str = Field(examples=["CTR"])
    tariff: str = Field(examples=["экспресс"])
    created_at: datetime
    status: str = Field(examples=["доставлен"])
    delivered_at: Optional[datetime] = None
    reschedule_to: Optional[datetime] = None


def _summary_dict(s):
    return {"total": s.total, "counted": s.counted, "on_time": s.on_time, "late": s.late,
            "open_late": s.open_late, "in_progress": s.in_progress, "excluded": s.excluded,
            "sla_pct": s.sla_pct, "p50_h": s.p50_h, "p90_h": s.p90_h, "avg_delay_h": s.avg_delay_h}


def _row_from_body(body: OrderIn) -> dict:
    row = {}
    for key, value in body.model_dump().items():
        if isinstance(value, datetime):
            value = value.isoformat()
        value = "" if value is None else str(value).strip()
        row[key] = VALUES.get(key, {}).get(value.lower(), value)
    return row


def create_app(get_repo, settings: Settings) -> FastAPI:
    app = FastAPI(title="SLA доставки", description="Конвейер агрегации заказов и расчёта SLA доставки")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")

    def period(date_from: Optional[date] = Query(None, alias="from"),
               date_to: Optional[date] = Query(None, alias="to"), zone: Optional[str] = None):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "начало периода позже конца")
        return {"date_from": date_from, "date_to": date_to, "zone": zone or None}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(request: Request, p=Depends(period), repo=Depends(get_repo)):
        zones = sorted(repo.zones().values(), key=lambda z: z.code)
        # фильтры из адресной строки: подборку можно отправить ссылкой
        return templates.TemplateResponse(request, "dashboard.html", {"zones": zones, "target": settings.sla_target,
                                                                      "f": p})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/zones")
    def zones(repo=Depends(get_repo)):
        return [z.__dict__ for z in sorted(repo.zones().values(), key=lambda z: z.code)]

    @app.get("/api/summary")
    def summary(p=Depends(period), repo=Depends(get_repo)):
        s = summarize(repo.results(**p))
        return {**_summary_dict(s), "target": settings.sla_target, "now": settings.now().isoformat()}

    @app.get("/api/daily")
    def daily(p=Depends(period), repo=Depends(get_repo)):
        return [{"day": d.isoformat(), **_summary_dict(s)} for d, s in by_day(repo.results(**p)).items()]

    @app.get("/api/by-zone")
    def zone_summary(p=Depends(period), repo=Depends(get_repo)):
        names = {z.code: z.name for z in repo.zones().values()}
        return [{"zone": code, "name": names.get(code, code), **_summary_dict(s)}
                for code, s in by_zone(repo.results(**p)).items()]

    @app.get("/api/late")
    def late(limit: int = Query(10, ge=1, le=100), p=Depends(period), repo=Depends(get_repo)):
        return repo.late_orders(limit, **p)

    @app.get("/api/rejected")
    def rejected(limit: int = Query(20, ge=1, le=200), repo=Depends(get_repo)):
        return repo.rejected(limit)

    @app.get("/api/orders")
    def orders(repo=Depends(get_repo)):
        """Все заказы с рассчитанным сроком и исходом SLA - для выгрузки в 1С."""
        results = {r.order_no: r for r in repo.results()}
        rows = []
        for o in repo.orders():
            r = results.get(o.order_no)
            rows.append({**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in o.__dict__.items()},
                         "deadline": r.deadline.isoformat() if r else None,
                         "outcome": r.outcome if r else None})
        return rows

    @app.post("/api/orders", status_code=201)
    def add_order(body: OrderIn, repo=Depends(get_repo)):
        rep = service.ingest([(1, _row_from_body(body))], repo, settings.now(), source="api", kind="api")
        if rep.rejected:
            raise HTTPException(422, rep.rejected[0][3])
        service.recompute(repo, settings.now())
        res = next(r for r in repo.results() if r.order_no == body.order_no)
        return {"order_no": res.order_no, "deadline": res.deadline.isoformat(), "outcome": res.outcome,
                "added": rep.added, "updated": rep.updated}

    @app.post("/api/recompute")
    def recompute(repo=Depends(get_repo)):
        daily_rows = service.recompute(repo, settings.now())
        return {"rows": len(daily_rows)}

    return app
