"""DEEPTERMINAL command-line interface.

Real companies (SEC EDGAR; set DEEPTERMINAL_SEC_USER_AGENT="Your Name you@example.com"):

    deepterminal lookup AAPL
    deepterminal fetch AAPL                           # cache filings data + show provenance summary
    deepterminal value AAPL --price 227.50 --price-as-of 2026-10-27 \\
        --price-source "Nasdaq official close" --discount-rate 0.085
    deepterminal verify examples/verification_manifest.json   # batch run, summary table
    deepterminal record AAPL KO CAT                    # save genuine responses for integration tests
    deepterminal serve out                             # browse generated reports/dashboards

Case files (synthetic fixture or hand-built):

    deepterminal analyze fixtures/synthetic_widget_corp.json --report out/report.md --dashboard out/dashboard.html
    deepterminal reverse-dcf fixtures/synthetic_widget_corp.json --solve margin
    deepterminal sec-facts --cik 320193 --as-of 2024-01-01
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from .data.case_file import load_case
from .data.http import FetchError
from .pipeline import run_case
from .valuation import reverse_dcf as rd

DEFAULT_CACHE = ".cache/sec"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print(f"  wrote {path}")


def _client(args: argparse.Namespace):
    from .data.sec_edgar import SECClient
    return SECClient(cache_dir=args.cache_dir, offline=args.offline)


def _payload(a) -> dict:
    s = a.scenarios
    return {
        "case_id": a.case.case_id, "company": a.case.company_name, "ticker": a.case.ticker,
        "synthetic": a.case.synthetic, "analysis_date": str(a.case.analysis_date),
        "price": {"value": a.case.share_price.value, "as_of": str(a.case.share_price.as_of),
                  "source": a.case.share_price.sources[0].title if a.case.share_price.sources else ""},
        "basis": a.case.latest_label,
        "market_enterprise_value_musd": a.market.enterprise_value,
        "diluted_shares_m": a.market.diluted_shares,
        "scenarios": {o.scenario.name: {"per_share": o.per_share, "enterprise_value": o.dcf.enterprise_value,
                                        "terminal_share": o.dcf.terminal_share} for o in s.outcomes},
        "reverse_dcf": [{"lever": r.lever, "status": r.status, "solutions": [p.value for p in r.solutions],
                         "held_constant": r.held_constant} for r in a.reverse],
        "verdict": a.assessment.verdict.value, "reasons": list(a.assessment.reasons),
        "assumptions": [v.to_dict() for v in a.case.assumptions],
        "validation": [c.__dict__ for c in a.case.data_validation.checks] if a.case.data_validation else [],
        "notes": a.case.notes,
        "citation_findings": [f.__dict__ for f in a.citations.findings],
    }


def _write_outputs(a, out_dir: Path) -> dict:
    from .reporting.dashboard import render_dashboard
    from .reporting.provenance import provenance_csv
    from .reporting.report import render_report
    payload = _payload(a)
    _write(out_dir / "report.md", render_report(a))
    _write(out_dir / "dashboard.html", render_dashboard(a))
    _write(out_dir / "result.json", json.dumps(payload, indent=2, default=str))
    _write(out_dir / "provenance.csv", provenance_csv(a.case))
    return payload


def _print_summary(a) -> None:
    c = a.case
    print(f"{c.company_name} ({c.ticker}) — price {c.share_price.value:,.2f} as of {c.share_price.as_of}; "
          f"basis {c.latest_label}")
    if c.data_validation is not None:
        print(f"  data validation: {c.data_validation.summary()}")
        for ch in c.data_validation.failures + c.data_validation.warnings:
            print(f"    {ch.status} {ch.name}: {ch.detail}")
    print(f"  market EV {a.market.enterprise_value:,.0f}m; diluted shares {a.market.diluted_shares:,.1f}m")
    for o in a.scenarios.outcomes:
        print(f"  {o.scenario.name:>4}: {o.per_share:10,.2f} per share (EV {o.dcf.enterprise_value:,.0f}m, "
              f"TV {o.dcf.terminal_share:.0%})")
    for r in a.reverse:
        sols = ", ".join(r.format_value(p.value) for p in r.solutions) or "none in bounds"
        print(f"  implied {r.lever_label}: {sols}")
    print(f"  verdict: {a.assessment.verdict.value}")
    if c.synthetic:
        print("  NOTE: synthetic fixture data — not a real company.")


# ───────────────────────────── commands ─────────────────────────────

def cmd_analyze(args: argparse.Namespace) -> int:
    from .reporting.dashboard import render_dashboard
    from .reporting.report import render_report
    a = run_case(load_case(args.case))
    _print_summary(a)
    if args.report:
        _write(Path(args.report), render_report(a))
    if args.dashboard:
        _write(Path(args.dashboard), render_dashboard(a))
    if args.json:
        _write(Path(args.json), json.dumps(_payload(a), indent=2, default=str))
    return 0


def cmd_reverse(args: argparse.Namespace) -> int:
    case = load_case(args.case)
    lever = rd.LEVERS[args.solve]()
    price = args.price if args.price is not None else float(case.share_price.value)
    r = rd.solve_implied(case.base_inputs, lever, price, case.capital,
                         float(case.tam_final_year.value) if case.tam_final_year else None)
    print(r.statement())
    for n in r.notes:
        print("  note:", n)
    for p in r.solutions:
        print(f"  final revenue {p.final_revenue:,.0f}; revenue CAGR "
              f"{'n/a' if p.revenue_cagr is None else f'{p.revenue_cagr:.2%}'}; final margin {p.final_margin:.2%}")
    return 0


def cmd_lookup(args: argparse.Namespace) -> int:
    from .data.sec_edgar import enrich_identity, recent_filings, resolve_company
    client = _client(args)
    for q in args.companies:
        ident = resolve_company(q, client, refresh=args.refresh)
        sub = client.submissions_result(ident.cik, args.refresh)
        ident = enrich_identity(ident, sub.json())
        print(f"{ident.ticker:<8} CIK {ident.cik:010d}  {ident.name}  SIC {ident.sic} {ident.sic_description or ''} "
              f" FYE {ident.fiscal_year_end}  exchanges {', '.join(ident.exchanges)}")
        for f in recent_filings(sub.json())[:4]:
            print(f"    {f.form:<5} filed {f.filed}  period {f.report_date}  {f.accession}  {f.url}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .data import sec_edgar as se
    client = _client(args)
    for q in args.companies:
        ident = se.resolve_company(q, client, refresh=args.refresh)
        client.submissions_result(ident.cik, args.refresh)
        res = client.companyfacts_result(ident.cik, args.refresh)
        facts = res.json()
        as_of = date.fromisoformat(args.as_of) if args.as_of else None
        annual = se.build_periods(facts, as_of=as_of, retrieved_at=res.retrieved_at)
        quarters = se.build_quarterly_periods(facts, as_of=as_of, retrieved_at=res.retrieved_at)
        ttm = se.build_ttm_period(facts, as_of=as_of, retrieved_at=res.retrieved_at)
        print(f"{ident.ticker} CIK {ident.cik:010d} {facts.get('entityName')}: retrieved {res.retrieved_at.isoformat()} "
              f"({'cache' if res.from_cache else 'network'}), sha256 {res.sha256[:12]}…")
        for p in annual[-5:]:
            prov = p.provenance["revenue"]
            print(f"  FY{p.fiscal_year} {p.period_start}–{p.period_end}: revenue {p.revenue:,.0f}m "
                  f"[{prov.concept}, {prov.form} {prov.accession}, filed {prov.filed}]")
        print(f"  {len(quarters)} discrete quarters"
              + (f"; latest {quarters[-1].period_end}" if quarters else ""))
        if ttm:
            print(f"  TTM {ttm.period_start}–{ttm.period_end}: revenue {ttm.revenue:,.0f}m")
    return 0


def _build_and_run(company: str, price: float, price_as_of: str, price_source: str, price_url: str | None,
                   settings, args: argparse.Namespace, analysis_date: date | None):
    from .data import sec_edgar as se
    from .data.http import OfflineCacheMiss
    from .data.sec_case import PriceQuote, build_sec_case
    client = _client(args)
    ident = se.resolve_company(company, client, refresh=args.refresh)
    try:
        ident = se.enrich_identity(ident, client.submissions_result(ident.cik, args.refresh).json())
    except OfflineCacheMiss:
        print("  note: submissions not cached; SIC-based financial-institution check skipped")
    res = client.companyfacts_result(ident.cik, args.refresh)
    quote = PriceQuote(price, date.fromisoformat(price_as_of), price_source, price_url)
    case = build_sec_case(res.json(), ident, quote, settings, analysis_date=analysis_date,
                          retrieved_at=res.retrieved_at)
    return run_case(case)


def _settings_from_args(args: argparse.Namespace):
    from .data.sec_case import ValuationSettings
    overrides = {"discount_rate": args.discount_rate, "terminal_growth": args.terminal_growth,
                 "terminal_roic": args.terminal_roic, "basis": args.basis}
    if args.settings:
        return ValuationSettings.from_json(args.settings, **overrides)
    if args.discount_rate is None:
        raise SystemExit("error: --discount-rate is required (or provide --settings with discount_rate); "
                         "DEEPTERMINAL does not invent a company's cost of capital")
    return ValuationSettings.from_dict({k: v for k, v in overrides.items() if v is not None} |
                                       ({"discount_rate_rationale": args.discount_rate_rationale}
                                        if args.discount_rate_rationale else {}))


def cmd_value(args: argparse.Namespace) -> int:
    if args.price_file:
        p = json.loads(Path(args.price_file).read_text())
        price, as_of, source, url = p["value"], p["as_of"], p["source"], p.get("url")
    else:
        if args.price is None or not args.price_as_of or not args.price_source:
            raise SystemExit("error: provide --price, --price-as-of and --price-source (or --price-file). "
                             "Live market data is not connected; the price must state where and when it was observed.")
        price, as_of, source, url = args.price, args.price_as_of, args.price_source, args.price_url
    a = _build_and_run(args.company, price, as_of, source, url, _settings_from_args(args), args,
                       date.fromisoformat(args.as_of) if args.as_of else None)
    _print_summary(a)
    _write_outputs(a, Path(args.out) / a.case.ticker)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Batch-run a manifest of companies; record what worked and what was blocked."""
    from .data.sec_case import ValuationSettings
    manifest = json.loads(Path(args.manifest).read_text())
    out = Path(args.out)
    rows = []
    for item in manifest["companies"]:
        name = item["company"]
        print(f"── {name}")
        pr = item.get("price") or {}
        if not all(pr.get(k) for k in ("value", "as_of", "source")):
            print("  NO_PRICE: price value/as_of/source not supplied in the manifest")
            rows.append((name, "NO_PRICE", "fill price.value, price.as_of and price.source with an observed price"))
            continue
        try:
            settings = ValuationSettings.from_dict(item["settings"])
            a = _build_and_run(name, pr["value"], pr["as_of"], pr["source"], pr.get("url"), settings, args,
                               date.fromisoformat(item["analysis_date"]) if item.get("analysis_date") else None)
            _print_summary(a)
            _write_outputs(a, out / a.case.ticker)
            base = a.scenarios.by_name("base").per_share
            rows.append((name, "OK", f"{a.case.latest_label}; validation {a.case.data_validation.summary()}; "
                         f"base {base:,.2f} vs price {a.case.share_price.value:,.2f}; {a.assessment.verdict.value}"))
        except (FetchError, ValueError, KeyError) as e:
            first = str(e).splitlines()[0]
            print(f"  {type(e).__name__}: {first}")
            rows.append((name, type(e).__name__, first))
    lines = ["# Real-company verification run", "", f"Run date: {date.today()}", "",
             "| Company | Status | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {s} | {d} |" for n, s, d in rows]
    _write(out / "verification_summary.md", "\n".join(lines) + "\n")
    return 0 if all(s == "OK" for _, s, _ in rows) else 3


def cmd_record(args: argparse.Namespace) -> int:
    """Fetch and copy genuine SEC responses (bytes + metadata) into a recordings directory."""
    from .data import sec_edgar as se
    client = _client(args)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    keys = ["company_tickers.json"]
    for q in args.companies:
        ident = se.resolve_company(q, client)
        client.submissions_result(ident.cik)
        client.companyfacts_result(ident.cik)
        keys += [f"submissions_{ident.cik:010d}.json.gz", f"companyfacts_{ident.cik:010d}.json.gz"]
    for k in dict.fromkeys(keys):
        for suffix in ("", ".meta.json"):
            src = Path(args.cache_dir) / (k + suffix)
            shutil.copy2(src, dest / (k + suffix))
            print(f"  recorded {dest / (k + suffix)}")
    print("Recorded responses are genuine SEC EDGAR data (US government public data). "
          "Integration tests in tests/integration read them offline.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import functools
    import http.server
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving {Path(args.directory).resolve()} at http://127.0.0.1:{args.port}/ (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


def cmd_sec(args: argparse.Namespace) -> int:
    from .data.sec_edgar import build_periods, detect_revisions, resolve_company
    client = _client(args)
    cik = args.cik if args.cik is not None else resolve_company(args.company, client).cik
    facts, retrieved = client.companyfacts(cik, refresh=args.refresh)
    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    print(f"{facts.get('entityName')} — retrieved {retrieved.isoformat()}; point-in-time as of {as_of or 'latest'}")
    for p in build_periods(facts, as_of=as_of, retrieved_at=retrieved):
        print(f"  FY{p.fiscal_year} (end {p.period_end}, filed {p.filed}): revenue {p.revenue:,.0f}m, "
              f"op income {p.operating_income:,.0f}m, OCF {p.operating_cash_flow:,.0f}m — {p.source_ref}")
    for r in detect_revisions(facts, as_of=as_of):
        print(f"  REVISION {r.field} {r.period_end}: {r.original:,.0f} → {r.revised:,.0f} (filed {r.revised_filed})")
    return 0


def _net(p: argparse.ArgumentParser) -> None:
    p.add_argument("--cache-dir", default=DEFAULT_CACHE, help=f"response cache (default {DEFAULT_CACHE})")
    p.add_argument("--offline", action="store_true", help="use cached/recorded responses only")
    p.add_argument("--refresh", action="store_true", help="ignore cache freshness and refetch")


def _valuation_opts(p: argparse.ArgumentParser) -> None:
    p.add_argument("--settings", help="JSON valuation settings (see examples/settings_template.json)")
    p.add_argument("--discount-rate", type=float, help="WACC, e.g. 0.085 (required unless in --settings)")
    p.add_argument("--discount-rate-rationale", help="how the discount rate was chosen")
    p.add_argument("--terminal-growth", type=float)
    p.add_argument("--terminal-roic", type=float)
    p.add_argument("--basis", choices=["ttm", "annual"])
    p.add_argument("--as-of", help="analysis date (point-in-time cut-off); default today")
    p.add_argument("--out", default="out", help="output directory (default out/)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deepterminal", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyse a case file (JSON)")
    a.add_argument("case")
    a.add_argument("--report")
    a.add_argument("--dashboard")
    a.add_argument("--json")
    a.set_defaults(fn=cmd_analyze)

    r = sub.add_parser("reverse-dcf", help="solve one lever implied by the price (case file)")
    r.add_argument("case")
    r.add_argument("--solve", choices=sorted(rd.LEVERS), default="growth")
    r.add_argument("--price", type=float)
    r.set_defaults(fn=cmd_reverse)

    lk = sub.add_parser("lookup", help="resolve tickers/CIKs via SEC EDGAR")
    lk.add_argument("companies", nargs="+")
    _net(lk)
    lk.set_defaults(fn=cmd_lookup)

    fe = sub.add_parser("fetch", help="fetch & cache SEC data; show periods with provenance")
    fe.add_argument("companies", nargs="+")
    fe.add_argument("--as-of")
    _net(fe)
    fe.set_defaults(fn=cmd_fetch)

    v = sub.add_parser("value", help="value a real company from SEC filings + a stated price")
    v.add_argument("company", help="ticker (AAPL) or CIK (320193)")
    v.add_argument("--price", type=float)
    v.add_argument("--price-as-of")
    v.add_argument("--price-source")
    v.add_argument("--price-url")
    v.add_argument("--price-file", help='JSON {"value":..,"as_of":"YYYY-MM-DD","source":"..","url":".."}')
    _valuation_opts(v)
    _net(v)
    v.set_defaults(fn=cmd_value)

    vf = sub.add_parser("verify", help="batch-run real companies from a manifest")
    vf.add_argument("manifest")
    vf.add_argument("--out", default="out/verification")
    _net(vf)
    vf.set_defaults(fn=cmd_verify)

    rc = sub.add_parser("record", help="save genuine SEC responses for offline integration tests")
    rc.add_argument("companies", nargs="+")
    rc.add_argument("--dest", default="tests/recorded/sec")
    _net(rc)
    rc.set_defaults(fn=cmd_record)

    sv = sub.add_parser("serve", help="serve an output directory on localhost")
    sv.add_argument("directory", nargs="?", default="out")
    sv.add_argument("--port", type=int, default=8765)
    sv.set_defaults(fn=cmd_serve)

    s = sub.add_parser("sec-facts", help="point-in-time annual financials from SEC EDGAR")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--cik", type=int)
    g.add_argument("--company")
    s.add_argument("--as-of")
    _net(s)
    s.set_defaults(fn=cmd_sec)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except FetchError as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    except (RuntimeError, ValueError) as e:   # missing User-Agent, insufficient/unsupported data
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
