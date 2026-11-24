"""Bear / base / bull scenario valuation and sensitivity analysis.

Probabilities are optional. A probability-weighted value is produced only
when probabilities are supplied *with* a calibration basis, and they must
sum to one. Without them the output is a range, never a fabricated average.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bridge import BridgeResult, CapitalStructure, equity_from_enterprise
from .dcf import DCFInputs, DCFResult, run_dcf

SCENARIO_ORDER = ("bear", "base", "bull")


@dataclass(frozen=True)
class Scenario:
    name: str                      # "bear" | "base" | "bull"
    narrative: str
    inputs: DCFInputs
    key_dependencies: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    probability: float | None = None


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario: Scenario
    dcf: DCFResult
    bridge: BridgeResult

    @property
    def per_share(self) -> float:
        return self.bridge.value_per_share


@dataclass(frozen=True)
class ScenarioSetResult:
    outcomes: tuple[ScenarioOutcome, ...]
    share_price: float
    weighted_value: float | None
    calibration_basis: str | None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def by_name(self, name: str) -> ScenarioOutcome:
        for o in self.outcomes:
            if o.scenario.name == name:
                return o
        raise KeyError(name)

    @property
    def value_range(self) -> tuple[float, float]:
        vals = [o.per_share for o in self.outcomes]
        return min(vals), max(vals)


def run_scenarios(scenarios: list[Scenario], cap: CapitalStructure, share_price: float,
                  calibration_basis: str | None = None) -> ScenarioSetResult:
    names = [s.name for s in scenarios]
    if sorted(names) != sorted(SCENARIO_ORDER):
        raise ValueError(f"expected exactly bear/base/bull scenarios, got {names}")
    scenarios = sorted(scenarios, key=lambda s: SCENARIO_ORDER.index(s.name))
    outcomes = []
    for s in scenarios:
        d = run_dcf(s.inputs)
        b = equity_from_enterprise(d.enterprise_value, cap, dilution_price=share_price)
        outcomes.append(ScenarioOutcome(s, d, b))

    warnings: list[str] = []
    vals = [o.per_share for o in outcomes]
    if not (vals[0] <= vals[1] <= vals[2]):
        warnings.append("scenario values are not ordered bear ≤ base ≤ bull; check inputs")
    negative = [o.scenario.name for o in outcomes if o.bridge.equity_value <= 0]
    if negative:
        warnings.append(f"{', '.join(negative)}: claims exceed the DCF enterprise value, so common equity has no "
                        "residual value and $0.00 per share is a floor, not an estimate. A DCF on current margins "
                        "and reinvestment is not informative here; test a recovery case in the assumptions")

    probs = [s.probability for s in scenarios]
    weighted = None
    if any(p is not None for p in probs):
        if any(p is None for p in probs):
            raise ValueError("either all scenarios have probabilities or none do")
        if abs(sum(probs) - 1.0) > 1e-9:
            raise ValueError(f"scenario probabilities sum to {sum(probs)}, not 1")
        if not (calibration_basis and calibration_basis.strip()):
            raise ValueError("probabilities require a stated calibration basis; "
                             "omit them to report a range instead")
        weighted = sum(p * v for p, v in zip(probs, vals))
    return ScenarioSetResult(tuple(outcomes), share_price, weighted,
                             calibration_basis if weighted is not None else None, tuple(warnings))


@dataclass(frozen=True)
class SensitivityGrid:
    row_label: str
    col_label: str
    rows: tuple[float, ...]
    cols: tuple[float, ...]
    values: tuple[tuple[float | None, ...], ...]     # per-share value; None = invalid region


def sensitivity_grid(base: DCFInputs, cap: CapitalStructure, share_price: float,
                     discount_rates: list[float], terminal_growths: list[float]) -> SensitivityGrid:
    """Per-share value across discount rate (rows) × terminal growth (columns)."""
    table = []
    for r in discount_rates:
        row = []
        for g in terminal_growths:
            if r <= g:
                row.append(None)
                continue
            d = run_dcf(base.with_changes(discount_rate=r, terminal_growth=g))
            row.append(equity_from_enterprise(d.enterprise_value, cap, share_price).value_per_share)
        table.append(tuple(row))
    return SensitivityGrid("discount rate", "terminal growth", tuple(discount_rates),
                           tuple(terminal_growths), tuple(table))


@dataclass(frozen=True)
class TornadoBar:
    assumption: str
    low_input: str
    high_input: str
    low_value: float
    high_value: float

    @property
    def swing(self) -> float:
        return abs(self.high_value - self.low_value)


def tornado(base: DCFInputs, cap: CapitalStructure, share_price: float,
            shocks: dict[str, tuple[DCFInputs, DCFInputs, str, str]]) -> list[TornadoBar]:
    """Rank assumptions by how much a plausible low/high change moves value.

    ``shocks`` maps an assumption name to (low_inputs, high_inputs,
    low_label, high_label). Use :func:`standard_shocks` for defaults.
    """
    bars = []
    for name, (lo, hi, lo_lbl, hi_lbl) in shocks.items():
        v_lo = equity_from_enterprise(run_dcf(lo).enterprise_value, cap, share_price).value_per_share
        v_hi = equity_from_enterprise(run_dcf(hi).enterprise_value, cap, share_price).value_per_share
        bars.append(TornadoBar(name, lo_lbl, hi_lbl, v_lo, v_hi))
    return sorted(bars, key=lambda b: b.swing, reverse=True)


def standard_shocks(base: DCFInputs, growth_pp: float = 0.03, margin_pp: float = 0.03,
                    rate_pp: float = 0.01, tg_pp: float = 0.005,
                    roic_rel: float = 0.25) -> dict[str, tuple[DCFInputs, DCFInputs, str, str]]:
    tm = base.terminal_ebit_margin if base.terminal_ebit_margin is not None else base.ebit_margin[-1]
    return {
        "revenue growth (every year)": (
            base.with_changes(revenue_growth=tuple(g - growth_pp for g in base.revenue_growth)),
            base.with_changes(revenue_growth=tuple(g + growth_pp for g in base.revenue_growth)),
            f"-{growth_pp:.0%} pts", f"+{growth_pp:.0%} pts"),
        "operating margin (incl. terminal)": (
            base.with_changes(ebit_margin=tuple(m - margin_pp for m in base.ebit_margin),
                              terminal_ebit_margin=tm - margin_pp),
            base.with_changes(ebit_margin=tuple(m + margin_pp for m in base.ebit_margin),
                              terminal_ebit_margin=tm + margin_pp),
            f"-{margin_pp:.0%} pts", f"+{margin_pp:.0%} pts"),
        "discount rate": (
            base.with_changes(discount_rate=base.discount_rate + rate_pp),
            base.with_changes(discount_rate=base.discount_rate - rate_pp),
            f"+{rate_pp:.0%} pts", f"-{rate_pp:.0%} pts"),
        "terminal growth": (
            base.with_changes(terminal_growth=base.terminal_growth - tg_pp),
            base.with_changes(terminal_growth=base.terminal_growth + tg_pp),
            f"-{tg_pp:.1%} pts", f"+{tg_pp:.1%} pts"),
        "terminal ROIC": (
            base.with_changes(terminal_roic=base.terminal_roic * (1 - roic_rel)),
            base.with_changes(terminal_roic=base.terminal_roic * (1 + roic_rel)),
            f"-{roic_rel:.0%}", f"+{roic_rel:.0%}"),
    }
