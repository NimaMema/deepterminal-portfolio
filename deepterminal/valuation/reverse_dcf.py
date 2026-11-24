"""Reverse DCF — what must happen for today's price to make financial sense?

A reverse DCF has one equation (model EV = market EV) and many unknowns, so
an "implied growth rate" only exists *conditional on* every other assumption.
This module therefore:

* solves for exactly one lever at a time and returns the assumptions that
  were held constant alongside the answer;
* scans the whole search interval and reports zero, one or several
  solutions (value is not monotonic in growth when ROIC < WACC);
* offers :func:`implied_surface` to show the *family* of (margin, growth)
  combinations consistent with the price — the honest picture when two
  assumptions are both unknown;
* treats growth *duration* as an integer search, not a continuous root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..finance.solvers import find_roots
from ..finance.timevalue import cagr, linear_path
from .bridge import CapitalStructure, market_enterprise_value
from .dcf import DCFInputs, DCFResult, SalesToCapital, ExplicitReinvestment, run_dcf


@dataclass(frozen=True)
class Lever:
    key: str
    label: str
    unit: str
    lower: float
    upper: float
    apply: Callable[[DCFInputs, float], DCFInputs]


def growth_with_fade(lower: float = -0.10, upper: float = 0.80) -> Lever:
    """Year-1 growth x, fading linearly to terminal growth by the final year."""
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        return inp.with_changes(revenue_growth=tuple(linear_path(x, inp.terminal_growth, inp.years)))
    return Lever("initial_growth_fading", "Year-1 revenue growth (fading to terminal)", "%",
                 lower, upper, apply)


def constant_growth(lower: float = -0.10, upper: float = 0.80) -> Lever:
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        return inp.with_changes(revenue_growth=(x,) * inp.years)
    return Lever("constant_growth", "Constant revenue growth over the forecast", "%",
                 lower, upper, apply)


def target_operating_margin(lower: float = -0.20, upper: float = 0.80) -> Lever:
    """Margin moves linearly from the year-1 margin to x by year N and stays there."""
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        path = tuple(linear_path(inp.ebit_margin[0], x, inp.years))
        return inp.with_changes(ebit_margin=path, terminal_ebit_margin=x)
    return Lever("target_operating_margin", "Steady-state operating (EBIT) margin", "%",
                 lower, upper, apply)


def terminal_margin(lower: float = -0.20, upper: float = 0.80) -> Lever:
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        return inp.with_changes(terminal_ebit_margin=x)
    return Lever("terminal_margin", "Terminal operating margin only", "%", lower, upper, apply)


def sales_to_capital(lower: float = 0.1, upper: float = 20.0) -> Lever:
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        if not isinstance(inp.reinvestment, SalesToCapital):
            raise ValueError("sales_to_capital lever requires SalesToCapital reinvestment")
        return inp.with_changes(reinvestment=SalesToCapital(x))
    return Lever("sales_to_capital", "Sales-to-capital (reinvestment efficiency)", "x",
                 lower, upper, apply)


def discount_rate(lower: float = 0.01, upper: float = 0.40) -> Lever:
    """Implied expected return (an IRR) if the forecast were exactly right."""
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        return inp.with_changes(discount_rate=x)
    return Lever("discount_rate", "Implied expected return (IRR on the forecast)", "%",
                 lower, upper, apply)


def terminal_growth(lower: float = -0.05, upper: float = 0.06) -> Lever:
    def apply(inp: DCFInputs, x: float) -> DCFInputs:
        return inp.with_changes(terminal_growth=x)
    return Lever("terminal_growth", "Terminal growth rate", "%", lower, upper, apply)


LEVERS: dict[str, Callable[[], Lever]] = {
    "growth": growth_with_fade,
    "constant_growth": constant_growth,
    "margin": target_operating_margin,
    "terminal_margin": terminal_margin,
    "sales_to_capital": sales_to_capital,
    "discount_rate": discount_rate,
    "terminal_growth": terminal_growth,
}


@dataclass(frozen=True)
class ImpliedPoint:
    value: float
    model: DCFResult
    final_revenue: float
    revenue_cagr: float | None
    final_margin: float
    cumulative_reinvestment: float
    cumulative_fcff: float
    implied_market_share: float | None


@dataclass(frozen=True)
class ReverseDCFResult:
    lever: str
    lever_label: str
    unit: str
    target_enterprise_value: float
    target_equity_value: float
    share_price: float
    status: str                 # "unique" | "multiple" | "none_in_bounds"
    solutions: tuple[ImpliedPoint, ...]
    held_constant: dict[str, str]
    bounds: tuple[float, float]
    value_range_in_bounds: tuple[float, float]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def format_value(self, x: float) -> str:
        return f"{x:.2%}" if self.unit == "%" else f"{x:.3g}{self.unit}"

    def statement(self) -> str:
        held = "; ".join(f"{k} = {v}" for k, v in self.held_constant.items())
        if self.status == "none_in_bounds":
            return (f"No value of {self.lever_label} within "
                    f"[{self.bounds[0]:g}, {self.bounds[1]:g}] reproduces the market price "
                    f"while holding: {held}.")
        vals = ", ".join(self.format_value(p.value) for p in self.solutions)
        prefix = "Multiple solutions" if self.status == "multiple" else "Conditional solution"
        return (f"{prefix}: {self.lever_label} = {vals}, holding: {held}. "
                "This is one point in a family of assumption sets consistent with the price, "
                "not a unique market forecast.")


def _fmt(v: float | tuple[float, ...], spec: str) -> str:
    vals = v if isinstance(v, tuple) else (v,)
    return ", ".join(format(x, spec) for x in vals)


def describe_assumptions(inp: DCFInputs, exclude: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if exclude not in ("initial_growth_fading", "constant_growth"):
        out["revenue growth path"] = ", ".join(f"{g:.1%}" for g in inp.revenue_growth)
    if exclude not in ("target_operating_margin",):
        out["EBIT margin path"] = ", ".join(f"{m:.1%}" for m in inp.ebit_margin)
    if exclude not in ("terminal_margin", "target_operating_margin"):
        tm = inp.terminal_ebit_margin if inp.terminal_ebit_margin is not None else inp.ebit_margin[-1]
        out["terminal margin"] = f"{tm:.1%}"
    if exclude != "discount_rate":
        out["discount rate"] = f"{inp.discount_rate:.2%}"
    if exclude != "terminal_growth":
        out["terminal growth"] = f"{inp.terminal_growth:.2%}"
    out["terminal ROIC"] = f"{inp.terminal_roic:.1%}"
    if exclude != "sales_to_capital":
        r = inp.reinvestment
        out["reinvestment"] = (f"sales-to-capital {_fmt(r.ratio, '.2f')}" if isinstance(r, SalesToCapital)
                               else f"net capex {_fmt(r.net_capex_pct_revenue, '.1%')} of revenue, "
                                    f"NWC {_fmt(r.nwc_pct_revenue_change, '.1%')} of revenue change")
    out["forecast horizon"] = f"{inp.years} years"
    return out


def _point(inp: DCFInputs, x: float, lever: Lever, tam: float | None) -> ImpliedPoint:
    res = run_dcf(lever.apply(inp, x))
    final = res.final_revenue
    try:
        growth = cagr(inp.base_revenue, final, inp.years)
    except ValueError:
        growth = None
    return ImpliedPoint(
        x, res, final, growth, res.years[-1].ebit_margin,
        sum(y.reinvestment for y in res.years), sum(y.fcff for y in res.years),
        final / tam if tam else None)


def solve_implied(base: DCFInputs, lever: Lever, share_price: float, cap: CapitalStructure,
                  total_addressable_market_final_year: float | None = None,
                  samples: int = 240) -> ReverseDCFResult:
    """Solve for the lever value(s) that make the DCF equal the market price."""
    market = market_enterprise_value(share_price, cap)
    target_ev = market.enterprise_value

    def f(x: float) -> float:
        return run_dcf(lever.apply(base, x)).enterprise_value - target_ev

    scan = find_roots(f, lever.lower, lever.upper, samples=samples)
    pts = tuple(_point(base, r, lever, total_addressable_market_final_year) for r in scan.roots)
    status = "none_in_bounds" if not pts else ("unique" if len(pts) == 1 else "multiple")
    notes: list[str] = []
    if not scan.monotonic:
        notes.append("model value is not monotonic in this lever over the search interval")
    if status == "none_in_bounds":
        hi = scan.max_value + target_ev
        lo = scan.min_value + target_ev
        notes.append(f"model EV ranges {lo:,.0f}–{hi:,.0f} over the interval versus market EV "
                     f"{target_ev:,.0f} (statement units)")
    for p in pts:
        if p.implied_market_share is not None and p.implied_market_share > 1:
            notes.append(f"solution {p.value:.4g} implies revenue above the stated addressable "
                         "market — economically implausible")
    return ReverseDCFResult(
        lever.key, lever.label, lever.unit, target_ev, market.equity_value, share_price, status, pts,
        describe_assumptions(base, lever.key), (lever.lower, lever.upper),
        (scan.min_value + target_ev, scan.max_value + target_ev), tuple(notes))


@dataclass(frozen=True)
class SurfacePoint:
    x: float
    y_solutions: tuple[float, ...]


def implied_surface(base: DCFInputs, x_lever: Lever, xs: list[float], y_lever: Lever,
                    share_price: float, cap: CapitalStructure) -> list[SurfacePoint]:
    """Iso-value curve: for each x (e.g. margin), the y (e.g. growth) matching the price."""
    out = []
    for x in xs:
        shifted = x_lever.apply(base, x)
        r = solve_implied(shifted, y_lever, share_price, cap, samples=120)
        out.append(SurfacePoint(x, tuple(p.value for p in r.solutions)))
    return out


@dataclass(frozen=True)
class DurationResult:
    growth_rate: float
    years_required: int | None
    max_years_tested: int
    enterprise_values: tuple[float, ...]
    target_enterprise_value: float


def implied_growth_duration(base: DCFInputs, growth_rate: float, share_price: float,
                            cap: CapitalStructure, max_years: int = 30) -> DurationResult:
    """Smallest number of years of ``growth_rate`` growth that justifies the price.

    Margins and tax for added years repeat the final explicit-year values.
    Returns ``years_required=None`` if no horizon up to ``max_years`` works.
    """
    target = market_enterprise_value(share_price, cap).enterprise_value
    evs = []
    found = None
    for n in range(1, max_years + 1):
        margins = tuple(base.ebit_margin[min(i, base.years - 1)] for i in range(n))
        tax = base.tax_rate if not isinstance(base.tax_rate, tuple) else tuple(
            base.tax_rate[min(i, base.years - 1)] for i in range(n))
        reinv = base.reinvestment
        if isinstance(reinv, SalesToCapital) and isinstance(reinv.ratio, tuple):
            reinv = SalesToCapital(tuple(reinv.ratio[min(i, base.years - 1)] for i in range(n)))
        if isinstance(reinv, ExplicitReinvestment):
            def pad(v):
                return v if not isinstance(v, tuple) else tuple(v[min(i, base.years - 1)] for i in range(n))
            reinv = ExplicitReinvestment(pad(reinv.net_capex_pct_revenue), pad(reinv.nwc_pct_revenue_change))
        inp = base.with_changes(revenue_growth=(growth_rate,) * n, ebit_margin=margins,
                                tax_rate=tax, reinvestment=reinv,
                                terminal_ebit_margin=(base.terminal_ebit_margin if base.terminal_ebit_margin is not None
                                                     else base.ebit_margin[-1]))
        ev = run_dcf(inp).enterprise_value
        evs.append(ev)
        if found is None and ev >= target:
            found = n
    return DurationResult(growth_rate, found, max_years, tuple(evs), target)
