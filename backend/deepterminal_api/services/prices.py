"""Free end-of-day prices (Stooq) stored as attributed price observations.

Prices are never invented: a stored quote is a close Stooq published for that date, labelled
with its source, retrieval time and the Stooq page. Fictional demo companies have no price.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se

from ..config import get_settings
from ..models import Company, PriceQuote
from . import companies as cs
from .free_sources import free_sources
from .gateway import DataUnavailable

ATTRIBUTION = {"stooq": "End-of-day prices from Stooq (stooq.com), free for non-commercial use.",
               "alphavantage": "End-of-day prices from Alpha Vantage (free tier)."}


LABEL = {"stooq": "Stooq", "alphavantage": "Alpha Vantage", "sec_form4": "SEC Form 4"}


def form4_price(db: Session, c: Company) -> tuple[date, float, str, str] | None:
    """Volume-weighted price of insiders' open-market trades (Form 4 codes S and P) on the latest trade date.

    A real, dated market transaction price from SEC filings: free and citable, but not an official close.
    It can lag by weeks when insiders have not traded recently; the valuation's freshness check applies."""
    from . import filings as fs
    trades = [t for t in fs.insider_transactions(db, c, limit=25)["transactions"]
              if t["code"] in ("S", "P") and t.get("price") and t.get("shares") and t.get("date")]
    if not trades:
        return None
    last = max(str(t["date"]) for t in trades)
    day = [t for t in trades if str(t["date"]) == last]
    vwap = sum(t["price"] * t["shares"] for t in day) / sum(t["shares"] for t in day)
    owners = sorted({t["owner"] for t in day})
    label = (f"SEC Form 4 open-market trades on {last}: volume-weighted {vwap:,.2f} across {len(day)} trade(s) "
             f"({', '.join(o.title() for o in owners[:3])}); insider-reported transaction price, not an official close")
    return date.fromisoformat(last), vwap, day[0]["url"], label


def _store(db: Session, c: Company, d: date, close: float, url: str, provider: str) -> PriceQuote:
    existing = db.scalar(select(PriceQuote).where(PriceQuote.company_id == c.id, PriceQuote.as_of == d,
                                                  PriceQuote.provider == provider))
    if existing:
        return existing
    p = PriceQuote(company_id=c.id, value=close, as_of=d, source=f"{LABEL[provider]} price {d.isoformat()}"
                   if provider == "sec_form4" else f"{LABEL[provider]} end-of-day close {d.isoformat()}",
                   url=url, provider=provider)
    db.add(p)
    return p


def fetch_prices(db: Session, c: Company, fiscal_year_ends: bool = True) -> dict:
    if c.synthetic:
        raise DataUnavailable("not_configured", "Demo companies are fictional and have no market price.",
                              "Enter a labelled demo price, or switch to live mode for real companies.")
    if get_settings().price_provider == "none":
        raise DataUnavailable("not_configured", "Automatic prices are disabled (DEEPTERMINAL_PRICE_PROVIDER=none).")
    if not c.ticker:
        raise DataUnavailable("not_found", "This company has no ticker to look up.")
    rows, res, provider, page, errors = None, None, None, None, []
    choice = get_settings().price_provider
    chain = ["stooq", "alphavantage", "sec_form4"] if choice == "auto" else [choice]
    for name in chain:
        if name == "alphavantage" and choice == "auto" and not get_settings().alphavantage_api_key:
            continue                     # optional free-key provider, only when configured
        try:
            if name == "sec_form4":
                got = form4_price(db, c)
                if not got:
                    raise DataUnavailable("not_found", "No recent open-market insider trades with prices.")
                d, px, url, label = got
                p = _store(db, c, d, px, url, "sec_form4")
                p.source = label
                db.commit()
                return {"latest": {"as_of": d.isoformat(), "close": px}, "stored": 1, "retrieved_at": None,
                        "from_cache": None, "source": url, "provider": "sec_form4",
                        "attribution": "Price from insiders' open-market trades reported on SEC Form 4 (free, US "
                                       "government public data). Not an official closing price.",
                        "errors": errors}
            if name == "stooq":
                rows, res = free_sources().stooq_daily(c.ticker)
                page = f"https://stooq.com/q/?s={free_sources().stooq_symbol(c.ticker)}"
            else:
                rows, res = free_sources().alphavantage_daily(c.ticker)
                page = f"https://www.alphavantage.co/ (TIME_SERIES_DAILY {c.ticker.upper()})"
            provider = name
            break
        except DataUnavailable as e:
            errors.append(f"{name}: {e.message}")
    if not rows:
        raise DataUnavailable("unavailable", "No free price source returned a close. " + " ".join(errors),
                              "Enter a price you observed (with date and source), or configure the free Alpha Vantage key "
                              "(DEEPTERMINAL_ALPHAVANTAGE_API_KEY).")
    last_d, last_close = rows[-1]
    stored = [_store(db, c, last_d, last_close, page, provider)]
    if fiscal_year_ends:
        # Close on (or the last trading day before) each fiscal year end: for multiple history.
        days = [d for d, _ in rows]
        facts, _ = cs.companyfacts(c)
        for end in list(se.annual_series(facts, "revenue", None, "latest"))[-10:]:
            i = bisect_right(days, end) - 1
            if i >= 0 and (end - days[i]).days <= 7:
                stored.append(_store(db, c, days[i], rows[i][1], page, provider))
    db.commit()
    return {"latest": {"as_of": last_d.isoformat(), "close": last_close}, "stored": len(stored),
            "retrieved_at": res.retrieved_at.isoformat(), "from_cache": res.from_cache,
            "source": page, "provider": provider, "attribution": ATTRIBUTION[provider], "errors": errors}
