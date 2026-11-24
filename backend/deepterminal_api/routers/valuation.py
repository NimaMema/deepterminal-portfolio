"""Valuation Laboratory and reverse DCF endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import public_demo as demo
from ..db import get_db
from ..models import ValuationRun
from ..services import valuation as vs
from ..services.gateway import DataUnavailable
from .companies import company_or_404

router = APIRouter(tags=["valuation"])


class PriceIn(BaseModel):
    value: float = Field(..., gt=0)
    as_of: date
    source: str = Field(..., min_length=3)
    url: str | None = None


class ValuationIn(BaseModel):
    settings: dict = Field(default_factory=dict, description="ValuationSettings overrides; discount_rate required")
    price: PriceIn | None = None
    as_of: date | None = None
    save: bool = False
    label: str | None = None


@router.post("/companies/{company_id}/valuation")
def run_valuation(company_id: int, body: ValuationIn, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    price = body.price.model_dump(mode="json") if body.price else None
    result = vs.value_company(db, c, body.settings, price, body.as_of)
    if body.save and demo.active():
        raise DataUnavailable("demo_readonly", "Saving runs needs the full local backend; the calculation above "
                              "works in the demo.")
    if body.save:
        result["run_id"] = vs.save_run(db, c, body.label, body.settings, price, result)
    return result


@router.get("/companies/{company_id}/valuation/runs")
def runs(company_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(ValuationRun).where(ValuationRun.company_id == company_id)
                      .order_by(ValuationRun.created_at.desc()).limit(50))
    return [{"id": r.id, "label": r.label, "settings": r.settings, "price": r.price, "created_at": r.created_at.isoformat(),
             "base": next((s["per_share"] for s in r.result.get("scenarios", []) if s["name"] == "base"), None),
             "verdict": (r.result.get("assessment") or {}).get("verdict")} for r in rows]


@router.get("/valuation/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(ValuationRun, run_id)
    return {"id": r.id, "label": r.label, "settings": r.settings, "price": r.price, "result": r.result}


class ShockIn(BaseModel):
    settings: dict
    revenue_shock: float = Field(0.15, ge=0, le=0.9)
    margin_shock: float = Field(0.03, ge=-0.2, le=0.5)
    years: int = Field(2, ge=1, le=7)
    price_offset: float = Field(0.0, ge=0, le=1)


@router.post("/companies/{company_id}/valuation/shock")
def shock(company_id: int, body: ShockIn, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    return vs.shock_scenario(db, c, body.settings, body.revenue_shock, body.margin_shock, body.years, body.price_offset)


class SegmentIn(BaseModel):
    name: str
    enterprise_value: float
    method: str
    source_note: str = ""


class SOTPIn(BaseModel):
    segments: list[SegmentIn]
    annual_corporate_cost: float = 0
    tax_rate: float = 0
    discount_rate: float | None = None
    growth: float = 0


@router.post("/valuation/sotp")
def sotp(body: SOTPIn):
    return vs.sotp(body.model_dump())


class AssetIn(BaseModel):
    name: str
    book_value: float
    recovery_rate: float = Field(..., ge=0)
    rationale: str = Field(..., min_length=3)


class NAVIn(BaseModel):
    assets: list[AssetIn]
    liabilities: float


@router.post("/valuation/nav")
def nav(body: NAVIn):
    return vs.nav(body.model_dump())
