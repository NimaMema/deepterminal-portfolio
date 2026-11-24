"""Forensic accounting screens: Piotroski F-Score, Beneish M-Score, Altman Z / Z''.

These are *screens*, not verdicts. A high M-Score is a statistical signal that
earnings manipulation was more likely among historical samples with similar
ratios; it is not evidence of wrongdoing. Every function returns its components
so the user can see which ratio drove the result, and returns ``None`` for any
component whose inputs are missing (no imputation).

Inputs are dicts of annual values for the current year (``c``) and prior year
(``p``) using DEEPTERMINAL field names (sec_edgar.CONCEPTS keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field

Year = dict[str, float | None]


def _g(d: Year, k: str) -> float | None:
    v = d.get(k)
    return None if v is None else float(v)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


@dataclass
class ScoreResult:
    name: str
    score: float | None
    components: dict[str, float | None]
    interpretation: str
    zone: str | None = None
    missing: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


def piotroski(c: Year, p: Year, pp: Year | None = None) -> ScoreResult:
    """Nine binary signals (Piotroski 2000). ``pp`` (two years back) gives average assets for ROA if present."""
    ta_c, ta_p = _g(c, "total_assets"), _g(p, "total_assets")
    roa_c = _div(_g(c, "net_income"), ta_p)
    roa_p = _div(_g(p, "net_income"), _g(pp, "total_assets") if pp else ta_p)
    cfo_c = _g(c, "operating_cash_flow")
    lev_c = _div(_g(c, "total_debt"), ta_c)
    lev_p = _div(_g(p, "total_debt"), ta_p)
    cr_c = _div(_g(c, "assets_current"), _g(c, "liabilities_current"))
    cr_p = _div(_g(p, "assets_current"), _g(p, "liabilities_current"))
    gm_c = _div(_g(c, "gross_profit"), _g(c, "revenue"))
    gm_p = _div(_g(p, "gross_profit"), _g(p, "revenue"))
    at_c = _div(_g(c, "revenue"), ta_p)
    at_p = _div(_g(p, "revenue"), _g(pp, "total_assets") if pp else ta_p)
    sh_c, sh_p = _g(c, "diluted_shares"), _g(p, "diluted_shares")

    def sig(cond):
        return None if cond is None else (1.0 if cond else 0.0)
    comps = {
        "roa_positive": sig(None if roa_c is None else roa_c > 0),
        "cfo_positive": sig(None if cfo_c is None else cfo_c > 0),
        "roa_improving": sig(None if roa_c is None or roa_p is None else roa_c > roa_p),
        "cfo_exceeds_net_income": sig(None if cfo_c is None or _g(c, "net_income") is None else cfo_c > _g(c, "net_income")),
        "leverage_falling": sig(None if lev_c is None or lev_p is None else lev_c <= lev_p),
        "current_ratio_rising": sig(None if cr_c is None or cr_p is None else cr_c > cr_p),
        "no_dilution": sig(None if sh_c is None or sh_p is None else sh_c <= sh_p * 1.001),
        "gross_margin_rising": sig(None if gm_c is None or gm_p is None else gm_c > gm_p),
        "asset_turnover_rising": sig(None if at_c is None or at_p is None else at_c > at_p),
    }
    missing = [k for k, v in comps.items() if v is None]
    score = sum(v for v in comps.values() if v is not None)
    known = 9 - len(missing)
    if known < 7:
        return ScoreResult("Piotroski F-Score", None, comps, f"insufficient data ({known}/9 signals computable)",
                           missing=missing)
    zone = "strong" if score >= 7 else ("weak" if score <= 3 else "moderate")
    return ScoreResult("Piotroski F-Score", score, comps,
                       f"{score:.0f} of {known} signals favourable ({zone} on Piotroski's 0–9 scale)", zone, missing,
                       ["Designed for value stocks; signals are binary and ignore magnitude."])


BENEISH_W = {"dsri": 0.920, "gmi": 0.528, "aqi": 0.404, "sgi": 0.892, "depi": 0.115, "sgai": -0.172,
             "tata": 4.679, "lvgi": -0.327}


def beneish(c: Year, p: Year) -> ScoreResult:
    """Beneish (1999) eight-variable M-Score. Above −1.78 is the conventional 'likely manipulator' cut-off."""
    rev_c, rev_p = _g(c, "revenue"), _g(p, "revenue")
    gm_c = _div(_g(c, "gross_profit"), rev_c)
    gm_p = _div(_g(p, "gross_profit"), rev_p)

    def aq(d):
        ca, ppe, ta = _g(d, "assets_current"), _g(d, "ppe_net"), _g(d, "total_assets")
        return None if None in (ca, ppe, ta) or ta == 0 else 1 - (ca + ppe) / ta

    def dep(d):
        dp, ppe = _g(d, "depreciation"), _g(d, "ppe_net")
        return None if dp is None or ppe is None or dp + ppe == 0 else dp / (dp + ppe)

    def lv(d):
        cl, ltd, ta = _g(d, "liabilities_current"), _g(d, "total_debt"), _g(d, "total_assets")
        return None if None in (cl, ltd, ta) or ta == 0 else (cl + ltd) / ta
    comps = {
        "dsri": _div(_div(_g(c, "accounts_receivable"), rev_c), _div(_g(p, "accounts_receivable"), rev_p)),
        "gmi": _div(gm_p, gm_c),
        "aqi": _div(aq(c), aq(p)),
        "sgi": _div(rev_c, rev_p),
        "depi": _div(dep(p), dep(c)),
        "sgai": _div(_div(_g(c, "sga"), rev_c), _div(_g(p, "sga"), rev_p)),
        "tata": None if None in (_g(c, "net_income"), _g(c, "operating_cash_flow"), _g(c, "total_assets"))
        else (_g(c, "net_income") - _g(c, "operating_cash_flow")) / _g(c, "total_assets"),
        "lvgi": _div(lv(c), lv(p)),
    }
    missing = [k for k, v in comps.items() if v is None]
    if missing:
        return ScoreResult("Beneish M-Score", None, comps, f"not computable: missing {', '.join(missing)}",
                           missing=missing, caveats=["No imputation is performed for missing inputs."])
    m = -4.84 + sum(BENEISH_W[k] * comps[k] for k in BENEISH_W)
    zone = "elevated" if m > -1.78 else "not elevated"
    return ScoreResult("Beneish M-Score", m, comps,
                       f"M = {m:.2f} ({'above' if m > -1.78 else 'below'} the −1.78 screening threshold)", zone, [],
                       ["Statistical screen from 1982–1992 manufacturing samples; high false-positive rate for fast "
                        "growers (SGI) and not applicable to financial firms.",
                        "A high score is not evidence of manipulation."])


def altman_z(c: Year, market_value_equity: float | None = None) -> ScoreResult:
    """Altman Z (public manufacturers, needs market value) or Z'' (book-equity, non-manufacturers)."""
    ta = _g(c, "total_assets")
    wc = None if _g(c, "assets_current") is None or _g(c, "liabilities_current") is None \
        else _g(c, "assets_current") - _g(c, "liabilities_current")
    x1 = _div(wc, ta)
    x2 = _div(_g(c, "retained_earnings"), ta)
    x3 = _div(_g(c, "operating_income"), ta)
    tl = _g(c, "total_liabilities")
    if market_value_equity is not None:
        x4 = _div(market_value_equity, tl)
        x5 = _div(_g(c, "revenue"), ta)
        comps = {"wc_ta": x1, "re_ta": x2, "ebit_ta": x3, "mve_tl": x4, "sales_ta": x5}
        missing = [k for k, v in comps.items() if v is None]
        if missing:
            return ScoreResult("Altman Z", None, comps, f"not computable: missing {', '.join(missing)}", missing=missing)
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        zone = "safe" if z > 2.99 else ("distress" if z < 1.81 else "grey")
        return ScoreResult("Altman Z", z, comps, f"Z = {z:.2f} ({zone} zone)", zone, [],
                           ["Original model for public manufacturers; uses market value of equity."])
    x4b = _div(_g(c, "shareholders_equity"), tl)
    comps = {"wc_ta": x1, "re_ta": x2, "ebit_ta": x3, "be_tl": x4b}
    missing = [k for k, v in comps.items() if v is None]
    if missing:
        return ScoreResult("Altman Z''", None, comps, f"not computable: missing {', '.join(missing)}", missing=missing)
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4b
    zone = "safe" if z > 2.6 else ("distress" if z < 1.1 else "grey")
    return ScoreResult("Altman Z''", z, comps, f"Z'' = {z:.2f} ({zone} zone)", zone, [],
                       ["Book-equity variant (no market price); thresholds 1.1 / 2.6.",
                        "Not designed for banks or insurers."])


def sloan_accruals(c: Year, p: Year) -> float | None:
    """(Net income − CFO) / average total assets."""
    ni, cfo = _g(c, "net_income"), _g(c, "operating_cash_flow")
    ta_c, ta_p = _g(c, "total_assets"), _g(p, "total_assets")
    if None in (ni, cfo, ta_c, ta_p) or ta_c + ta_p == 0:
        return None
    return (ni - cfo) / ((ta_c + ta_p) / 2)
