"""Market Expectations dashboard (spec §3 "Required Interface", §14 Reverse DCF / Expectations Gap).

Renders a self-contained HTML file (no external requests) with the eight
required panels:

1. current market value            5. industry comparisons
2. base-case intrinsic value range 6. sensitivity analysis
3. market-implied assumptions      7. critical assumptions
4. historical operating performance 8. downside if expectations are missed

Every number is computed in Python by the deterministic engine; the page's
JavaScript only shows tooltips, so the dashboard can never disagree with
the report.
"""

from __future__ import annotations

import html
import json

from ..pipeline import CaseAnalysis
from .provenance import provenance_rows

W, H = 560, 260
PAD_L, PAD_R, PAD_T, PAD_B = 56, 20, 16, 40


def _e(s: object) -> str:
    return html.escape(str(s), quote=True)


def _pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def _money(x: float | None, d: int = 0) -> str:
    return "n/a" if x is None else f"{x:,.{d}f}"


class Scale:
    def __init__(self, d0: float, d1: float, r0: float, r1: float):
        if d1 == d0:
            d1 = d0 + 1
        self.d0, self.d1, self.r0, self.r1 = d0, d1, r0, r1

    def __call__(self, v: float) -> float:
        return self.r0 + (v - self.d0) / (self.d1 - self.d0) * (self.r1 - self.r0)


def _ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    step = (hi - lo) / (n - 1)
    return [lo + step * i for i in range(n)]


def _padded(vals: list[float], frac: float = 0.08) -> tuple[float, float]:
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or abs(hi) or 1.0
    return lo - span * frac, hi + span * frac


def _axes(x: Scale, y: Scale, xt: list[float], yt: list[float], xfmt, yfmt,
          xlabel: str, ylabel: str) -> str:
    parts = []
    for t in yt:
        parts.append(f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
                     f'<text class="tick" x="{PAD_L - 6}" y="{y(t) + 4:.1f}" text-anchor="end">{_e(yfmt(t))}</text>')
    for t in xt:
        parts.append(f'<text class="tick" x="{x(t):.1f}" y="{H - PAD_B + 16}" text-anchor="middle">{_e(xfmt(t))}</text>')
    parts.append(f'<line class="axis" x1="{PAD_L}" x2="{W - PAD_R}" y1="{H - PAD_B}" y2="{H - PAD_B}"/>')
    parts.append(f'<text class="axlabel" x="{(PAD_L + W - PAD_R) / 2}" y="{H - 6}" text-anchor="middle">{_e(xlabel)}</text>')
    parts.append(f'<text class="axlabel" transform="translate(12,{(PAD_T + H - PAD_B) / 2}) rotate(-90)" '
                 f'text-anchor="middle">{_e(ylabel)}</text>')
    return "".join(parts)


def _svg(body: str, label: str) -> str:
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{_e(label)}" '
            f'preserveAspectRatio="xMidYMid meet">{body}</svg>')


def value_range_chart(a: CaseAnalysis) -> str:
    s = a.scenarios
    price = s.share_price
    vals = [o.per_share for o in s.outcomes] + [price]
    lo, hi = _padded(vals, 0.12)
    lo = max(lo, 0)
    x = Scale(lo, hi, PAD_L, W - PAD_R)
    h = 150
    yb = 70
    parts = []
    for t in _ticks(lo, hi, 6):
        parts.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="20" y2="{h - 30}"/>'
                     f'<text class="tick" x="{x(t):.1f}" y="{h - 12}" text-anchor="middle">{t:,.0f}</text>')
    bear, base, bull = (s.by_name(n).per_share for n in ("bear", "base", "bull"))
    parts.append(f'<rect class="range" x="{x(bear):.1f}" y="{yb - 9}" width="{x(bull) - x(bear):.1f}" '
                 f'height="18" rx="4" data-tip="Scenario range: {bear:,.2f} – {bull:,.2f} per share"/>')
    for n, v in (("Bear", bear), ("Base", base), ("Bull", bull)):
        parts.append(f'<circle class="mark s1 hit" cx="{x(v):.1f}" cy="{yb}" r="6" '
                     f'data-tip="{n} case: {v:,.2f} per share ({v / price - 1:+.0%} vs price)"/>'
                     f'<text class="lbl" x="{x(v):.1f}" y="{yb - 16}" text-anchor="middle">{n} {v:,.2f}</text>')
    parts.append(f'<line class="price" x1="{x(price):.1f}" x2="{x(price):.1f}" y1="24" y2="{h - 34}"/>'
                 f'<text class="lbl strong" x="{x(price) + 6:.1f}" y="{yb + 30}" text-anchor="start">'
                 f'Price {price:,.2f}</text>')
    return (f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="Scenario value range versus price">'
            + "".join(parts) + "</svg>")


def iso_value_chart(a: CaseAnalysis) -> str:
    pts = [(p.x, p.y_solutions[0]) for p in a.surface if p.y_solutions]
    if len(pts) < 2:
        return "<p class='muted'>Not enough solutions in bounds to draw the iso-value curve.</p>"
    base = a.case.base_inputs
    hist = a.statements.latest()
    xs = [p[0] for p in pts] + [hist.operating_margin]
    ys = [p[1] for p in pts] + [base.revenue_growth[0]]
    if hist.revenue_growth is not None:
        ys.append(hist.revenue_growth)
    x = Scale(*_padded(xs), PAD_L, W - PAD_R)
    y = Scale(*_padded(ys), H - PAD_B, PAD_T)
    body = _axes(x, y, _ticks(*_padded(xs)), _ticks(*_padded(ys)), lambda t: f"{t:.0%}",
                 lambda t: f"{t:.0%}", "Steady-state operating margin", "Implied year-1 growth")
    d = " ".join(f"{'M' if i == 0 else 'L'}{x(px):.1f},{y(py):.1f}" for i, (px, py) in enumerate(pts))
    body += f'<path class="line s1" d="{d}"/>'
    for px, py in pts:
        body += (f'<circle class="dot s1 hit" cx="{x(px):.1f}" cy="{y(py):.1f}" r="4" '
                 f'data-tip="Margin {px:.1%} → growth {py:.1%} justifies the price"/>')
    bx, by = base.ebit_margin[-1], base.revenue_growth[0]
    body += (f'<circle class="dot s2 hit" cx="{x(bx):.1f}" cy="{y(by):.1f}" r="6" '
             f'data-tip="Base case: margin {bx:.1%}, year-1 growth {by:.1%}"/>'
             f'<text class="lbl" x="{x(bx) + 9:.1f}" y="{y(by) - 8:.1f}">Base case</text>')
    if hist.revenue_growth is not None:
        hx, hy = hist.operating_margin, hist.revenue_growth
        body += (f'<rect class="dot s3 hit" x="{x(hx) - 5:.1f}" y="{y(hy) - 5:.1f}" width="10" height="10" rx="2" '
                 f'data-tip="Latest reported FY{hist.fiscal_year}: margin {hx:.1%}, growth {hy:.1%}"/>'
                 f'<text class="lbl" x="{x(hx) + 9:.1f}" y="{y(hy) + 16:.1f}">FY{hist.fiscal_year} actual</text>')
    body += (f'<text class="lbl" x="{x(pts[0][0]) + 8:.1f}" y="{y(pts[0][1]) + 4:.1f}">'
             'Combinations the price implies</text>')
    return _svg(body, "Iso-value curve of margin and growth combinations consistent with the price")


def history_chart(a: CaseAnalysis, metric: str) -> str:
    ms = [m for m in a.statements.metrics if getattr(m, metric) is not None]
    if not ms:
        return "<p class='muted'>No history.</p>"
    gap = next((g for g in a.gap if g.metric == ("operating margin" if metric == "operating_margin"
                                                  else "revenue CAGR")), None)
    implied = gap.market_implied if gap else None
    yrs = [m.fiscal_year for m in ms]
    vals = [getattr(m, metric) for m in ms]
    y_lo, y_hi = _padded(vals + ([implied] if implied is not None else []) + [0.0])
    x = Scale(min(yrs) - 0.3, max(yrs) + 0.3, PAD_L, W - PAD_R)
    y = Scale(y_lo, y_hi, H - PAD_B, PAD_T)
    body = _axes(x, y, [float(v) for v in yrs], _ticks(y_lo, y_hi), lambda t: f"FY{int(t)}",
                 lambda t: f"{t:.0%}", "Fiscal year",
                 "Operating margin" if metric == "operating_margin" else "Revenue growth")
    bw = min(36, (W - PAD_L - PAD_R) / len(yrs) * 0.5)
    for yr, v in zip(yrs, vals):
        top, base = (y(v), y(0)) if v >= 0 else (y(0), y(v))
        body += (f'<rect class="bar s1 hit" x="{x(yr) - bw / 2:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                 f'height="{max(base - top, 1):.1f}" rx="4" data-tip="FY{yr}: {v:.1%} (reported)"/>')
    if implied is not None:
        body += (f'<line class="ref s2" x1="{PAD_L}" x2="{W - PAD_R}" y1="{y(implied):.1f}" y2="{y(implied):.1f}"/>'
                 f'<rect class="hitline" x="{PAD_L}" y="{y(implied) - 6:.1f}" width="{W - PAD_L - PAD_R}" height="12" '
                 f'data-tip="Market-implied {gap.metric}: {implied:.1%} (conditional on base-case assumptions)"/>'
                 f'<text class="lbl" x="{W - PAD_R - 4}" y="{y(implied) - 6:.1f}" text-anchor="end">'
                 f'Market-implied {implied:.1%}</text>')
    return _svg(body, f"Historical {metric.replace('_', ' ')} versus market-implied level")


def peer_chart(a: CaseAnalysis) -> str:
    peers = a.case.peers_operating
    if not peers:
        return "<p class='muted'>No peer operating data supplied.</p>"
    hist = a.statements.latest()
    g, m = a.reverse[0], a.reverse[1]
    implied = (g.solutions[0].revenue_cagr if g.solutions else None,
               m.solutions[0].value if m.solutions else None)
    xs = [p.operating_margin for p in peers] + [hist.operating_margin]
    ys = [p.revenue_growth for p in peers] + [hist.revenue_growth or 0]
    if implied[0] is not None:
        ys.append(implied[0])
    if implied[1] is not None:
        xs.append(implied[1])
    x = Scale(*_padded(xs), PAD_L, W - PAD_R)
    y = Scale(*_padded(ys), H - PAD_B, PAD_T)
    body = _axes(x, y, _ticks(*_padded(xs)), _ticks(*_padded(ys)), lambda t: f"{t:.0%}",
                 lambda t: f"{t:.0%}", "Operating margin", "Revenue growth")
    for p in peers:
        body += (f'<circle class="dot s1 hit" cx="{x(p.operating_margin):.1f}" cy="{y(p.revenue_growth):.1f}" r="5" '
                 f'data-tip="{_e(p.name)}: growth {p.revenue_growth:.1%}, margin {p.operating_margin:.1%}"/>'
                 f'<text class="lbl muted" x="{x(p.operating_margin) + 8:.1f}" y="{y(p.revenue_growth) + 4:.1f}">'
                 f'{_e(p.name.replace("Synthetic ", ""))}</text>')
    hx, hy = hist.operating_margin, hist.revenue_growth or 0
    body += (f'<rect class="dot s3 hit" x="{x(hx) - 5:.1f}" y="{y(hy) - 5:.1f}" width="10" height="10" rx="2" '
             f'data-tip="{_e(a.case.ticker)} FY{hist.fiscal_year} actual: growth {hy:.1%}, margin {hx:.1%}"/>')
    if implied[0] is not None:
        # Growth-implied point: margin held at base path's final margin.
        bm = a.case.base_inputs.ebit_margin[-1]
        body += (f'<path class="dot s2 hit" d="M{x(bm):.1f},{y(implied[0]) - 7:.1f} l7,7 l-7,7 l-7,-7 z" '
                 f'data-tip="Market-implied revenue CAGR {implied[0]:.1%} at base margin {bm:.1%}"/>'
                 f'<text class="lbl" x="{x(bm) - 10:.1f}" y="{y(implied[0]) + 4:.1f}" text-anchor="end">Market-implied</text>')
    return _svg(body, "Peer growth and margin versus company and market-implied expectations")


def _diverging_style(t: float) -> str:
    """t in [-1, 1]: negative = below price (red pole), positive = above (blue pole)."""
    t = max(-1.0, min(1.0, t))
    pole = "var(--div-pos)" if t >= 0 else "var(--div-neg)"
    pct = abs(t) * 100
    ink = "#ffffff" if abs(t) > 0.6 else "var(--text-primary)"
    return f"fill:color-mix(in oklab, {pole} {pct:.0f}%, var(--div-mid));--ink:{ink}"


def heatmap(a: CaseAnalysis) -> str:
    sg = a.sensitivity
    price = a.scenarios.share_price
    cw, ch = 88, 34
    left, top = 70, 30
    w = left + cw * len(sg.cols) + 10
    hgt = top + ch * len(sg.rows) + 40
    parts = []
    for j, g in enumerate(sg.cols):
        parts.append(f'<text class="tick" x="{left + cw * j + cw / 2}" y="{top - 10}" text-anchor="middle">g {g:.1%}</text>')
    for i, (r, row) in enumerate(zip(sg.rows, sg.values)):
        parts.append(f'<text class="tick" x="{left - 8}" y="{top + ch * i + ch / 2 + 4}" text-anchor="end">r {r:.1%}</text>')
        for j, v in enumerate(row):
            xx, yy = left + cw * j, top + ch * i
            if v is None:
                parts.append(f'<rect x="{xx + 1}" y="{yy + 1}" width="{cw - 2}" height="{ch - 2}" rx="4" class="na"/>')
                continue
            t = (v / price - 1) / 0.5
            parts.append(
                f'<g class="hit" data-tip="Discount rate {r:.1%}, terminal growth {sg.cols[j]:.1%}: '
                f'{v:,.2f} per share ({v / price - 1:+.0%} vs price)">'
                f'<rect x="{xx + 1}" y="{yy + 1}" width="{cw - 2}" height="{ch - 2}" rx="4" style="{_diverging_style(t)}"/>'
                f'<text class="cell" x="{xx + cw / 2}" y="{yy + ch / 2 + 4}" text-anchor="middle">{v:,.1f}</text></g>')
    parts.append(f'<text class="axlabel" x="{left}" y="{hgt - 12}">Red: below today\'s price · grey: ≈ price · '
                 'blue: above (scale saturates at ±50%)</text>')
    return (f'<svg viewBox="0 0 {w} {hgt}" role="img" aria-label="Sensitivity of value per share to '
            f'discount rate and terminal growth">' + "".join(parts) + "</svg>")


def tornado_chart(a: CaseAnalysis) -> str:
    bars = a.tornado
    base = a.scenarios.by_name("base").per_share
    vals = [b.low_value for b in bars] + [b.high_value for b in bars] + [base]
    lo, hi = _padded(vals, 0.1)
    left, right = 190, 30
    w = 560
    x = Scale(lo, hi, left, w - right)
    rh = 34
    hgt = 30 + rh * len(bars) + 30
    parts = []
    for t in _ticks(lo, hi, 5):
        parts.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="20" y2="{hgt - 26}"/>'
                     f'<text class="tick" x="{x(t):.1f}" y="{hgt - 10}" text-anchor="middle">{t:,.0f}</text>')
    for i, b in enumerate(bars):
        yy = 26 + rh * i
        parts.append(f'<text class="lbl" x="{left - 8}" y="{yy + 15}" text-anchor="end">{_e(b.assumption)}</text>')
        for v, inp, cls in ((b.low_value, b.low_input, "s2"), (b.high_value, b.high_input, "s1")):
            x0, x1 = sorted((x(base), x(v)))
            parts.append(f'<rect class="bar {cls} hit" x="{x0:.1f}" y="{yy + 3}" width="{max(x1 - x0, 1):.1f}" '
                         f'height="18" rx="4" data-tip="{_e(b.assumption)} {inp}: {v:,.2f} per share"/>')
    parts.append(f'<line class="axis" x1="{x(base):.1f}" x2="{x(base):.1f}" y1="20" y2="{hgt - 26}"/>')
    return (f'<svg viewBox="0 0 {w} {hgt}" role="img" aria-label="Tornado chart of valuation sensitivity">'
            + "".join(parts) + "</svg>")


CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--panel:#ffffff;--border:#e4e3df;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#77766f;--grid:#ecebe7;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;
--div-pos:#2a78d6;--div-neg:#e34948;--div-mid:#f0efec;--warn-bg:#fff4dc;--warn-ink:#6b4a00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface:#141413;
--panel:#1a1a19;--border:#2e2e2b;--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#9a9990;
--grid:#2a2a27;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--div-pos:#3987e5;--div-neg:#e66767;--div-mid:#383835;
--warn-bg:#3a2e10;--warn-ink:#f3d58a}}
:root[data-theme="dark"]{color-scheme:dark;--surface:#141413;--panel:#1a1a19;--border:#2e2e2b;
--text-primary:#f0efec;--text-secondary:#c3c2b7;--text-muted:#9a9990;--grid:#2a2a27;--s1:#3987e5;
--s2:#d95926;--s3:#199e70;--div-pos:#3987e5;--div-neg:#e66767;--div-mid:#383835;--warn-bg:#3a2e10;--warn-ink:#f3d58a}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text-primary);
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:0 0 2px}
.sub{color:var(--text-secondary);margin:0 0 16px}
.banner{background:var(--warn-bg);color:var(--warn-ink);border-radius:8px;padding:10px 14px;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:16px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px;min-width:0}
.panel .desc{color:var(--text-secondary);margin:0 0 10px;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile .k{color:var(--text-secondary);font-size:12px}.tile .v{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.tile .n{color:var(--text-muted);font-size:12px}
svg{width:100%;height:auto;display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}.axis{stroke:var(--text-muted);stroke-width:1}
.tick,.axlabel{fill:var(--text-muted);font-size:11px}.lbl{fill:var(--text-secondary);font-size:12px}
.lbl.strong{fill:var(--text-primary);font-weight:600}.muted{color:var(--text-muted);fill:var(--text-muted)}
.s1{fill:var(--s1);stroke:var(--s1)}.s2{fill:var(--s2);stroke:var(--s2)}.s3{fill:var(--s3);stroke:var(--s3)}
.line{fill:none;stroke-width:2}.dot,.mark{stroke:var(--panel);stroke-width:2}.bar{stroke:var(--panel);stroke-width:2}
.ref{stroke-width:2;stroke-dasharray:6 4;fill:none}.hitline{fill:transparent}
.range{fill:var(--grid)}.price{stroke:var(--text-primary);stroke-width:2;stroke-dasharray:3 3}
.cell{fill:var(--ink);font-size:12px;font-variant-numeric:tabular-nums}.na{fill:var(--grid)}
.hit{cursor:default}.hit:hover{opacity:.85}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:6px 8px;border-bottom:1px solid var(--border);text-align:right;vertical-align:top}
th:first-child,td:first-child{text-align:left}th{color:var(--text-secondary);font-weight:600}
.tablewrap{overflow-x:auto}
.prov td,.prov th{white-space:nowrap;text-align:left}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:6px 0 0;color:var(--text-secondary);font-size:12px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.verdict{font-size:16px;font-weight:600}
details{margin-top:8px;color:var(--text-secondary)}summary{cursor:pointer}
#tip{position:fixed;pointer-events:none;background:var(--text-primary);color:var(--panel);padding:6px 9px;
border-radius:6px;font-size:12px;max-width:300px;opacity:0;transition:opacity .08s;z-index:9}
"""

JS = """
const tip=document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el=>{
 el.addEventListener('mousemove',e=>{tip.textContent=el.dataset.tip;tip.style.opacity=1;
  const x=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8);tip.style.left=x+'px';tip.style.top=(e.clientY+14)+'px'});
 el.addEventListener('mouseleave',()=>{tip.style.opacity=0});
});
"""


def _legend(items: list[tuple[str, str]]) -> str:
    return '<div class="legend">' + "".join(
        f'<span><i style="background:var(--{c})"></i>{_e(t)}</span>' for c, t in items) + "</div>"


def render_dashboard(a: CaseAnalysis) -> str:
    c = a.case
    s = a.scenarios
    price = s.share_price
    asmt = a.assessment
    bear = s.by_name("bear")
    p = []
    w = p.append
    w(f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
      f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
      f"<title>Market Expectations · {_e(c.ticker)}</title><style>{CSS}</style></head><body><main>")
    w(f"<h1>Market Expectations — {_e(c.company_name)} ({_e(c.ticker)})</h1>")
    w(f"<p class='sub'>Price {price:,.2f} {_e(c.currency)} as of <b>{_e(c.share_price.as_of)}</b> · analysis date "
      f"{_e(c.analysis_date)} · latest financials {_e(c.latest_label)} (filed {_e(c.latest_period.filed)}) · "
      f"figures in {_e(c.currency)} {_e(c.units)}</p>")
    if c.synthetic:
        w(f"<div class='banner'><b>Synthetic data.</b> {_e(c.disclaimer)}</div>")

    # 1 current market value
    w("<section class='panel'><h2>1 · Current market value</h2>"
      f"<p class='desc'>Market price as of {_e(c.share_price.as_of)}; diluted by treasury stock method at that price.</p>"
      "<div class='tiles'>")
    for k, v, n in (("Share price", f"{price:,.2f}", f"as of {c.share_price.as_of}"),
                    ("Diluted shares", f"{a.market.diluted_shares:,.1f}", "millions"),
                    ("Market cap", _money(a.market.equity_value), c.units.split(" ")[0]),
                    ("Enterprise value", _money(a.market.enterprise_value), "market cap + net claims"),
                    ("EV / EBITDA", f"{a.multiples['EV/EBITDA'].value:.1f}x" if a.multiples['EV/EBITDA'].meaningful else "n/m",
                     f"trailing {c.latest_label}")):
        w(f"<div class='tile'><div class='k'>{_e(k)}</div><div class='v'>{_e(v)}</div><div class='n'>{_e(n)}</div></div>")
    w("</div></section>")

    w("<div class='grid2' style='margin-top:16px'>")
    # 2 value range
    w("<section class='panel'><h2>2 · Intrinsic value range</h2>"
      "<p class='desc'>Bear / base / bull DCF values per share against today's price. No probability weighting "
      + ("(none supplied with a calibration basis)." if s.weighted_value is None else
         f"— weighted {s.weighted_value:,.2f} ({_e(s.calibration_basis)}).") + "</p>")
    w(value_range_chart(a))
    w(f"<p class='verdict'>{_e(asmt.verdict.value)}</p><ul class='desc'>{''.join(f'<li>{_e(r)}</li>' for r in asmt.reasons)}</ul></section>")

    # 3 implied assumptions
    w("<section class='panel'><h2>3 · Market-implied operating assumptions</h2>"
      "<p class='desc'>Each row solves one lever with everything else held at the base case. Together they are "
      "alternatives, not a joint forecast. The curve shows the whole family of margin/growth pairs the price implies.</p>")
    w(iso_value_chart(a))
    w(_legend([("s1", "Price-consistent combinations"), ("s2", "Base case"), ("s3", "Latest reported")]))
    w("<div class='tablewrap'><table><tr><th>Lever solved</th><th>Implied</th><th>Base case</th><th>Status</th></tr>")
    base_in = c.base_inputs
    base_vals = {"initial_growth_fading": base_in.revenue_growth[0], "target_operating_margin": base_in.ebit_margin[-1],
                 "discount_rate": base_in.discount_rate}
    for r in a.reverse:
        imp = ", ".join(_pct(x.value) for x in r.solutions) or "none in bounds"
        w(f"<tr><td>{_e(r.lever_label)}</td><td>{_e(imp)}</td><td>{_pct(base_vals.get(r.lever))}</td><td>{_e(r.status)}</td></tr>")
    d = a.duration
    w(f"<tr><td>Years of {d.growth_rate:.1%} growth required</td><td>"
      f"{d.years_required if d.years_required else '> ' + str(d.max_years_tested)}</td><td>{base_in.years}</td><td>integer search</td></tr>")
    w("</table></div><details><summary>Assumptions held constant</summary><ul>"
      + "".join(f"<li>{_e(k)}: {_e(v)}</li>" for k, v in a.reverse[0].held_constant.items()) + "</ul></details></section>")

    # 4 historical performance
    w("<section class='panel'><h2>4 · Historical operating performance vs. expectations</h2>"
      "<p class='desc'>Reported results (bars) against the level the price implies (dashed). "
      "Implied values are conditional on the base-case assumptions.</p>")
    w(history_chart(a, "revenue_growth"))
    w(history_chart(a, "operating_margin"))
    w(_legend([("s1", "Reported"), ("s2", "Market-implied")]))
    w("</section>")

    # 5 industry comparisons
    w("<section class='panel'><h2>5 · Industry comparisons</h2>"
      "<p class='desc'>Peer growth and margin (latest), the company's latest year, and the market-implied revenue CAGR.</p>")
    w(peer_chart(a))
    w(_legend([("s1", "Peers"), ("s3", f"{c.ticker} latest"), ("s2", "Market-implied")]))
    w("<div class='tablewrap'><table><tr><th>Metric</th><th>Implied</th><th>Co. median</th><th>Co. best</th>"
      "<th>Peer median</th><th>Peer best</th></tr>")
    for g in a.gap:
        w(f"<tr><td>{_e(g.metric)}</td><td>{_pct(g.market_implied)}</td><td>{_pct(g.company_median)}</td>"
          f"<td>{_pct(g.company_max)}</td><td>{_pct(g.peer_median)}</td><td>{_pct(g.peer_max)}</td></tr>")
    w("</table></div><ul>" + "".join(f"<li>{_e(o)}</li>" for g in a.gap for o in g.observations) + "</ul></section>")

    # 6 sensitivity
    w("<section class='panel'><h2>6 · Sensitivity analysis</h2>"
      "<p class='desc'>Base-case value per share by discount rate (rows) and terminal growth (columns). "
      "Shows how much of the conclusion depends on interest-rate-sensitive inputs.</p>")
    w(heatmap(a))
    w("</section>")

    # 7 critical assumptions
    w("<section class='panel'><h2>7 · Critical assumptions</h2>"
      "<p class='desc'>Value per share when each assumption is moved alone; bars start at the base value.</p>")
    w(tornado_chart(a))
    w(_legend([("s2", "Unfavourable change"), ("s1", "Favourable change")]))
    w("</section>")

    # 8 downside
    w("<section class='panel'><h2>8 · Downside if expectations are missed</h2>"
      "<p class='desc'>Bear-case outcome and what it assumes.</p><div class='tiles'>"
      f"<div class='tile'><div class='k'>Bear value / share</div><div class='v'>{bear.per_share:,.2f}</div>"
      f"<div class='n'>{bear.per_share / price - 1:+.0%} vs price</div></div>"
      f"<div class='tile'><div class='k'>Bear EV</div><div class='v'>{_money(bear.dcf.enterprise_value)}</div>"
      f"<div class='n'>vs market EV {_money(a.market.enterprise_value)}</div></div></div>"
      f"<p>{_e(bear.scenario.narrative)}</p><p class='desc'>Depends on: {_e('; '.join(bear.scenario.key_dependencies))}</p>"
      "</section>")
    w("</div>")

    # data table view for accessibility
    w("<section class='panel' style='margin-top:16px'><h2>Scenario table</h2><div class='tablewrap'><table>"
      "<tr><th></th><th>Bear</th><th>Base</th><th>Bull</th></tr>")
    rows = [("Final-year revenue", lambda o: _money(o.dcf.final_revenue)),
            ("Final EBIT margin", lambda o: _pct(o.dcf.years[-1].ebit_margin)),
            ("Discount rate", lambda o: _pct(o.dcf.inputs.discount_rate, 2)),
            ("Terminal growth", lambda o: _pct(o.dcf.inputs.terminal_growth)),
            ("Terminal share of EV", lambda o: _pct(o.dcf.terminal_share, 0)),
            ("Equity value", lambda o: _money(o.bridge.equity_value)),
            ("Value per share", lambda o: f"{o.per_share:,.2f}")]
    for label, fn in rows:
        w(f"<tr><td>{_e(label)}</td>" + "".join(f"<td>{_e(fn(o))}</td>" for o in s.outcomes) + "</tr>")
    w("</table></div><p class='desc'>Citation audit: " + _e(f"{a.citations.checked} values checked, "
      f"{len(a.citations.findings)} finding(s)") + ". " + _e(asmt.caveat) + "</p></section>")
    if c.data_validation is not None or provenance_rows(c):
        w("<section class='panel' style='margin-top:16px'><h2>Data provenance &amp; validation</h2>"
          "<p class='desc'>Every reported figure, the XBRL concept and filing it came from, and when it was retrieved.</p>")
        if c.data_validation is not None:
            w(f"<p><b>Validation:</b> {_e(c.data_validation.summary())}</p><ul>"
              + "".join(f"<li><b>{_e(ch.status)}</b> {_e(ch.name)}: {_e(ch.detail)}</li>" for ch in c.data_validation.checks)
              + "</ul>")
        if c.notes:
            w("<details><summary>Data handling notes</summary><ul>"
              + "".join(f"<li>{_e(n)}</li>" for n in c.notes) + "</ul></details>")
        rows = provenance_rows(c)
        if rows:
            w("<details><summary>Figure provenance (" + str(len(rows)) + " figures)</summary><div class='tablewrap'><table class='prov'>"
              "<tr><th>Figure</th><th>Period</th><th>Value</th><th>Concept</th><th>Filing</th><th>Filed</th>"
              "<th>Retrieved</th><th>Derivation</th></tr>")
            for r in rows:
                w(f"<tr><td>{_e(r['figure'])}</td><td>{_e(r['period'])}</td><td>{_e(r['value'])} {_e(r['unit'])}</td>"
                  f"<td>{_e(r['concept'])}</td><td><a href='{_e(r['source_url'])}'>{_e(r['form'])} {_e(r['accession'])}</a></td>"
                  f"<td>{_e(r['filed'])}</td><td>{_e(r['retrieved_at'][:19])}</td>"
                  f"<td title='{_e(r['derivation_inputs'])}'>{_e(r['derivation'] or '—')}</td></tr>")
            w("</table></div></details>")
        w("</section>")
    w(f"<div id='tip' role='status'></div><script>{JS}</script>")
    w("<script type='application/json' id='analysis-data'>" +
      json.dumps({"ticker": c.ticker, "price": price, "price_as_of": str(c.share_price.as_of),
                  "scenarios": {o.scenario.name: o.per_share for o in s.outcomes},
                  "verdict": asmt.verdict.value}).replace("</", "<\\/") + "</script>")
    w("</main></body></html>")
    return "".join(p)
