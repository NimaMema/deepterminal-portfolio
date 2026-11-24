"""Sum-of-the-parts and asset-based valuation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    name: str
    enterprise_value: float
    method: str            # e.g. "EV/EBITDA 9.0x on segment EBITDA", "segment DCF"
    source_note: str = ""


@dataclass(frozen=True)
class SOTPResult:
    segments: tuple[Segment, ...]
    gross_value: float
    capitalised_corporate_costs: float
    enterprise_value: float


def sum_of_the_parts(segments: list[Segment], annual_corporate_cost: float = 0.0,
                     tax_rate: float = 0.0, discount_rate: float | None = None,
                     growth: float = 0.0) -> SOTPResult:
    """Sum segment EVs and deduct capitalised unallocated head-office costs.

    Head-office cost is a real claim on segment cash flows; ignoring it is a
    common source of inflated SOTP values. Capitalised as
    cost × (1 - tax) / (r - g).
    """
    if not segments:
        raise ValueError("at least one segment is required")
    gross = sum(s.enterprise_value for s in segments)
    cap = 0.0
    if annual_corporate_cost:
        if discount_rate is None or discount_rate <= growth:
            raise ValueError("capitalising corporate costs needs discount_rate > growth")
        cap = annual_corporate_cost * (1 - tax_rate) / (discount_rate - growth)
    return SOTPResult(tuple(segments), gross, cap, gross - cap)


@dataclass(frozen=True)
class AssetLine:
    name: str
    book_value: float
    recovery_rate: float      # 1.0 = book, 0.5 = 50% haircut, >1 = mark-up with evidence
    rationale: str


@dataclass(frozen=True)
class AssetValuation:
    assets: tuple[AssetLine, ...]
    adjusted_assets: float
    liabilities: float
    net_asset_value: float


def adjusted_net_asset_value(assets: list[AssetLine], liabilities: float) -> AssetValuation:
    """Liquidation/replacement-style NAV: Σ book × recovery − liabilities."""
    for a in assets:
        if a.recovery_rate < 0:
            raise ValueError(f"negative recovery for {a.name}")
        if not a.rationale.strip():
            raise ValueError(f"recovery assumption for {a.name} needs a rationale")
    adj = sum(a.book_value * a.recovery_rate for a in assets)
    return AssetValuation(tuple(assets), adj, liabilities, adj - liabilities)
