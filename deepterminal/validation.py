"""Data-quality checks run on every real-company dataset before valuation.

Each check returns PASS / WARN / FAIL with the numbers it compared, so a
reviewer can see *why* data was trusted. Checks compare figures that were
reported independently (e.g. a 9-month YTD fact against the sum of three
separately tagged quarters); tautological checks (Q4 derived from FY then
summed back to FY) are deliberately not used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .data import sec_edgar as se


@dataclass(frozen=True)
class Check:
    name: str
    status: str          # "PASS" | "WARN" | "FAIL"
    detail: str


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "FAIL"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "WARN"]

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        n = {s: sum(1 for c in self.checks if c.status == s) for s in ("PASS", "WARN", "FAIL")}
        return f"{n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail"


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


def validate_companyfacts(facts: dict[str, Any], as_of: date | None, analysis_date: date,
                          min_years: int = 3, tol: float = 0.005) -> ValidationReport:
    rep = ValidationReport()
    try:
        se.check_supported(facts)
        rep.add("supported filer", "PASS", "us-gaap facts in USD")
    except se.UnsupportedFiler as e:
        rep.add("supported filer", "FAIL", str(e))
        return rep

    annual = se.build_periods(facts, as_of=as_of)
    status = "PASS" if len(annual) >= min_years else ("WARN" if annual else "FAIL")
    rep.add("annual history", status,
            f"{len(annual)} complete fiscal years (need ≥{min_years}); "
            + (f"{annual[0].period_end}–{annual[-1].period_end}" if annual else "none"))

    # Balance-sheet identity: Assets = Liabilities + Equity (both reported tags)
    assets = se.annual_series(facts, "total_assets", as_of, "latest")
    le = se.annual_series(facts, "liabilities_and_equity", as_of, "latest")
    common = sorted(set(assets) & set(le))[-5:]
    if common:
        worst = max(common, key=lambda d: _rel(assets[d].value, le[d].value))
        r = _rel(assets[worst].value, le[worst].value)
        rep.add("balance sheet identity", "PASS" if r <= tol else "FAIL",
                f"Assets vs LiabilitiesAndStockholdersEquity over {len(common)} year-ends; worst gap {r:.3%} at {worst}")
    else:
        rep.add("balance sheet identity", "WARN", "LiabilitiesAndStockholdersEquity not tagged")

    # Independent tie-out: 9M YTD fact vs sum of three separately tagged 3-month quarters
    ties = 0
    bad, revised = [], []
    for concept in se.CONCEPTS["revenue"][0]:
        fs = [f for f in se.iter_facts(facts, concept, "USD")
              if f.start and f.form in se.QUARTERLY_FORMS + se.ANNUAL_FORMS
              and (as_of is None or f.filed <= as_of)]
        # Compare like with like: each 9M figure as first reported, against the quarters as they were
        # known on that filing date. Later filings restate comparatives, so mixing vintages flags
        # restatements as tie-out failures.
        first_9m: dict[tuple, se.Fact] = {}
        for f in sorted(fs, key=lambda f: f.filed):
            if 260 <= f.days <= 285:
                first_9m.setdefault((f.start, f.end), f)
        for f in first_9m.values():
            known: dict[tuple, float] = {}       # quarters as known on the 9M filing date
            latest: dict[tuple, float] = {}      # quarters as currently reported (restatements applied)
            for q in sorted(fs, key=lambda q: q.filed):
                if 80 <= q.days <= 100 and q.start >= f.start and q.end <= f.end:
                    latest[(q.start, q.end)] = q.value
                    if q.filed <= f.filed:
                        known[(q.start, q.end)] = q.value
            if len(known) != 3:
                continue
            ties += 1
            tot_known, tot_latest = sum(known.values()), sum(latest.values())
            if _rel(tot_known, f.value) <= tol:
                continue
            if len(latest) == 3 and _rel(tot_latest, f.value) <= tol:
                changed = [f"{e}: {known[(s, e)]:,.0f}→{latest[(s, e)]:,.0f}" for (s, e) in known
                           if _rel(known[(s, e)], latest[(s, e)]) > tol]
                revised.append(f"{concept} 9M to {f.end} ties only after later revision of quarter(s) "
                               + ", ".join(changed))
            else:
                bad.append(f"{concept} 9M to {f.end}: {f.value:,.0f} vs Σquarters {tot_known:,.0f}")
        if ties:
            break
    if ties:
        rep.add("quarterly tie-out", "FAIL" if bad else ("WARN" if revised else "PASS"),
                f"{ties} nine-month periods compared with three reported quarters"
                + (f"; mismatches: {'; '.join(bad[:3])}" if bad else "")
                + (f"; explained by restatement: {'; '.join(revised[:3])}" if revised else ""))
    else:
        rep.add("quarterly tie-out", "WARN", "no independently reported quarters to compare")

    # Competing revenue concepts reported for the same year
    tags = {}
    for concept in se.CONCEPTS["revenue"][0][:2]:
        fs = [f for f in se.iter_facts(facts, concept, "USD") if f.start and 350 <= f.days - 1 <= 380
              and f.form in se.ANNUAL_FORMS and (as_of is None or f.filed <= as_of)]
        tags[concept] = {f.end: f.value for f in fs}
    a, b = tags.values()
    both = sorted(set(a) & set(b))[-5:]
    diffs = [(d, a[d], b[d]) for d in both if _rel(a[d], b[d]) > 0.02]
    if diffs:
        d, x, y = diffs[-1]
        rep.add("revenue concept consistency", "WARN",
                f"Revenues ({x:,.0f}) and RevenueFromContractWithCustomer ({y:,.0f}) differ at {d}; "
                "'Revenues' (total) is used")
    elif both:
        rep.add("revenue concept consistency", "PASS", f"{len(both)} years agree within 2%")

    # Sign and magnitude sanity
    problems = []
    for p in annual:
        if p.revenue <= 0:
            problems.append(f"FY{p.fiscal_year} revenue ≤ 0")
        if p.capex < 0:
            problems.append(f"FY{p.fiscal_year} capex negative (sign convention)")
        if abs(p.net_income) > 5 * abs(p.revenue):
            problems.append(f"FY{p.fiscal_year} |net income| > 5× revenue")
        if p.diluted_shares <= 0:
            problems.append(f"FY{p.fiscal_year} diluted shares missing")
    rep.add("sign & magnitude sanity", "WARN" if problems else "PASS", "; ".join(problems) or "ok")

    # Restatements
    all_revs = se.detect_revisions(facts, as_of=as_of)
    revs = [r for r in all_revs if r.kind == "revision"]
    splits = sorted({f"×{r.split_ratio:g}" for r in all_revs if r.kind == "stock_split"})
    scale = [r for r in all_revs if r.kind == "scale_correction"]
    rep.add("restatements / revisions", "WARN" if revs else "PASS",
            f"{len(revs)} revised annual figure(s)" + (": " + "; ".join(
                f"{r.field} {r.period_end} {r.original:,.0f}→{r.revised:,.0f}" for r in revs[-3:]) if revs else "")
            + (f"; share counts restated for stock split(s) {', '.join(splits)} (not a restatement)" if splits else "")
            + (f"; {len(scale)} value(s) re-tagged at a different scale (×1,000 tagging corrections)" if scale else ""))

    # Staleness of the latest filing
    filed = [p.filed for p in annual if p.filed]
    ttm = se.build_ttm_period(facts, as_of=as_of)
    if ttm and ttm.filed:
        filed.append(ttm.filed)
    if filed:
        age = (analysis_date - max(filed)).days
        rep.add("data freshness", "PASS" if age <= 120 else "WARN",
                f"latest filing used was filed {max(filed)} ({age} days before {analysis_date})")
    rep.add("TTM availability", "PASS" if ttm else "WARN",
            f"TTM to {ttm.period_end}" if ttm else "four contiguous quarters not available; annual basis only")
    return rep
