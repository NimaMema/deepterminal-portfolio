"""Saved research: watchlist, saved investigations, reports, valuations, notes, theses."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Company, SavedItem
from ..services.gateway import DataUnavailable

router = APIRouter(tags=["workspace"])


class SavedIn(BaseModel):
    company_id: int | None = None
    kind: str = Field(..., pattern="^(watchlist|investigation|report|valuation|note|thesis|chat)$")
    ref_id: str | None = Field(None, max_length=64)
    title: str = Field(..., min_length=1, max_length=256)
    notes: str = Field("", max_length=20000)
    tags: list[str] = Field(default_factory=list)


class SavedPatch(BaseModel):
    title: str | None = Field(None, max_length=256)
    notes: str | None = Field(None, max_length=20000)
    tags: list[str] | None = None


def item_dict(i: SavedItem, c: Company | None) -> dict:
    return {"id": i.id, "company_id": i.company_id, "company": {"name": c.name, "ticker": c.ticker,
                                                               "synthetic": c.synthetic} if c else None,
            "kind": i.kind, "ref_id": i.ref_id, "title": i.title, "notes": i.notes, "tags": i.tags,
            "created_at": i.created_at.isoformat(), "updated_at": i.updated_at.isoformat()}


@router.get("/saved")
def list_saved(kind: str | None = None, company_id: int | None = None, db: Session = Depends(get_db)):
    q = select(SavedItem, Company).outerjoin(Company, Company.id == SavedItem.company_id).order_by(SavedItem.updated_at.desc())
    if kind:
        q = q.where(SavedItem.kind == kind)
    if company_id:
        q = q.where(SavedItem.company_id == company_id)
    return [item_dict(i, c) for i, c in db.execute(q.limit(500)).all()]


@router.post("/saved")
def create_saved(body: SavedIn, db: Session = Depends(get_db)):
    if body.kind == "watchlist":
        existing = db.scalar(select(SavedItem).where(SavedItem.kind == "watchlist", SavedItem.company_id == body.company_id))
        if existing:
            return item_dict(existing, db.get(Company, existing.company_id))
    i = SavedItem(**body.model_dump())
    db.add(i)
    db.commit()
    return item_dict(i, db.get(Company, i.company_id) if i.company_id else None)


@router.patch("/saved/{item_id}")
def update_saved(item_id: int, body: SavedPatch, db: Session = Depends(get_db)):
    i = db.get(SavedItem, item_id)
    if i is None:
        raise DataUnavailable("not_found", "saved item not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(i, k, v)
    db.commit()
    return item_dict(i, db.get(Company, i.company_id) if i.company_id else None)


@router.delete("/saved/{item_id}")
def delete_saved(item_id: int, db: Session = Depends(get_db)):
    db.execute(delete(SavedItem).where(SavedItem.id == item_id))
    db.commit()
    return {"ok": True}
