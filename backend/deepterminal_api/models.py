"""ORM models. Alembic migrations in backend/alembic are generated from these.

Evidence discipline is encoded in the schema: every Evidence row points at a
Source (with publication and retrieval times) and carries an epistemic status
and a verification status; Findings reference Evidence ids.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Computed, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return uuid.uuid4().hex


EPISTEMIC = ("historical_fact", "company_statement", "corroborated_fact", "third_party_report", "estimate",
             "model_assumption", "analytical_inference", "speculative_scenario", "unverified_claim")
VERIFICATION = ("verified", "unverified", "failed", "not_applicable")


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cik: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    ticker: Mapped[str | None] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(256))
    sic: Mapped[str | None] = mapped_column(String(8), index=True)
    sic_description: Mapped[str | None] = mapped_column(String(256))
    state_of_incorporation: Mapped[str | None] = mapped_column(String(64))
    fiscal_year_end: Mapped[str | None] = mapped_column(String(8))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(128))
    ein: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(256))
    exchanges: Mapped[list] = mapped_column(JSONType, default=list)
    former_names: Mapped[list] = mapped_column(JSONType, default=list)
    addresses: Mapped[dict] = mapped_column(JSONType, default=dict)
    first_filing_date: Mapped[date | None] = mapped_column(Date)   # earliest EDGAR filing, incl. older index pages
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TickerIndex(Base):
    """Searchable ticker/CIK/name list (SEC company_tickers.json or demo set)."""
    __tablename__ = "ticker_index"
    cik: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (Index("ix_ticker_index_ticker", "ticker"),)


class DataFetch(Base):
    """Audit log of every external retrieval attempt (success or failure)."""
    __tablename__ = "data_fetches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adapter: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))       # ok | cache | blocked | denied | not_found | error
    sha256: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    detail: Mapped[str | None] = mapped_column(Text)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    kind: Mapped[str] = mapped_column(String(48))         # sec_filing | sec_xbrl | user_input | computation | provider
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date | None] = mapped_column(Date)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[date | None] = mapped_column(Date)
    accession: Mapped[str | None] = mapped_column(String(32), index=True)
    licence: Mapped[str | None] = mapped_column(String(256))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    sha256: Mapped[str | None] = mapped_column(String(64))


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(48))         # financial_fact | excerpt | computed | filing_event | user_note
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    locator: Mapped[str | None] = mapped_column(Text)     # XBRL concept+period, section+offset, table row...
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    period_end: Mapped[date | None] = mapped_column(Date)
    epistemic_status: Mapped[str] = mapped_column(String(32))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")
    limitations: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source: Mapped[Source | None] = relationship(lazy="joined")


class Filing(Base):
    __tablename__ = "filings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    accession: Mapped[str] = mapped_column(String(32), unique=True)
    form: Mapped[str] = mapped_column(String(32), index=True)
    filed: Mapped[date] = mapped_column(Date, index=True)
    report_date: Mapped[date | None] = mapped_column(Date)
    primary_document: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(Text)
    items: Mapped[list] = mapped_column(JSONType, default=list)   # 8-K item codes
    size: Mapped[int | None] = mapped_column(Integer)
    text_status: Mapped[str] = mapped_column(String(24), default="not_fetched")  # not_fetched|fetched|failed
    text_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class FilingSection(Base):
    __tablename__ = "filing_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(32))          # item_1, item_1a, item_3, item_7, full, ...
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    tsv = mapped_column(TSVECTOR(), Computed(
        "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(text, ''))", persisted=True))
    __table_args__ = (UniqueConstraint("filing_id", "key"),
                      Index("ix_filing_sections_tsv", "tsv", postgresql_using="gin"))


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))         # investigation | module | thesis | report
    modules: Mapped[list] = mapped_column(JSONType, default=list)
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued|running|succeeded|failed|cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_step: Mapped[str | None] = mapped_column(String(256))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    level: Mapped[str] = mapped_column(String(12), default="info")
    module: Mapped[str | None] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONType, default=dict)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    module: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    epistemic_status: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))     # positive | neutral | watch | concern | unavailable
    confidence: Mapped[str] = mapped_column(String(16))   # high | medium | low
    evidence_ids: Mapped[list] = mapped_column(JSONType, default=list)
    limitations: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
    generated_by: Mapped[str] = mapped_column(String(64))  # rules | anthropic:<model> | openai:<model>
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PriceQuote(Base):
    __tablename__ = "price_quotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    value: Mapped[float] = mapped_column(Float)
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(48), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ValuationRun(Base):
    __tablename__ = "valuation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(256))
    settings: Mapped[dict] = mapped_column(JSONType)
    price: Mapped[dict] = mapped_column(JSONType)
    result: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Peer(Base):
    __tablename__ = "peers"
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    peer_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True)
    relation: Mapped[str] = mapped_column(String(16), default="direct")    # direct | indirect
    rationale: Mapped[str] = mapped_column(Text, default="")
    added_by: Mapped[str] = mapped_column(String(32), default="user")


class EntityLink(Base):
    """Supply-chain / corporate relationship graph edge, always evidence-backed."""
    __tablename__ = "entity_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    graph: Mapped[str] = mapped_column(String(24))        # supply_chain | corporate
    entity: Mapped[str] = mapped_column(String(256))
    entity_type: Mapped[str] = mapped_column(String(32))  # supplier | manufacturer | customer | subsidiary | country | material
    relation: Mapped[str] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64))
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"))
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified")
    job_id: Mapped[str | None] = mapped_column(String(32))


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSONType, default=list)
    generated_by: Mapped[str | None] = mapped_column(String(64))
    usage: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    sections: Mapped[list] = mapped_column(JSONType, default=list)
    html: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SavedItem(Base):
    __tablename__ = "saved_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))         # watchlist | investigation | report | valuation | note | thesis
    ref_id: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)


class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    job_id: Mapped[str | None] = mapped_column(String(32))
