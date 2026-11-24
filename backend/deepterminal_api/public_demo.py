"""Hosted public demo: keep visitors' own runs private to them.

The demo database is a fixed snapshot restored before the API starts. Anything created after
that (a visitor's chat or Thesis Challenger run) is reachable by its unguessable id only, and is
left out of shared listings, so one visitor never sees another's input.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import ResearchJob
from .services.gateway import DataUnavailable

BOOT = datetime.now(timezone.utc)


def active() -> bool:
    return get_settings().public_demo


def visitor_job_ids(db: Session, company_id: int | None = None) -> set[str]:
    if not active():
        return set()
    q = select(ResearchJob.id).where(ResearchJob.created_at > BOOT)
    if company_id is not None:
        q = q.where(ResearchJob.company_id == company_id)
    return set(db.scalars(q))


def check_job(db: Session, kind: str) -> None:
    """Visitors may run the rule-based Thesis Challenger only, one job at a time across the demo."""
    if not active():
        return
    if kind != "thesis":
        raise DataUnavailable("demo_readonly", "Investigations need the full local backend; the public demo shows "
                              "recorded investigations. Try the Thesis Challenger instead.")
    running = db.scalars(select(ResearchJob.id).where(ResearchJob.status.in_(("queued", "running")))).all()
    if len(running) >= get_settings().demo_max_running_jobs:
        raise DataUnavailable("rate_limited", "Another visitor's Thesis Challenger run is in progress. "
                              "Try again in a minute.")
