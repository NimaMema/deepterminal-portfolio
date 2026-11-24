"""Enterprise value ↔ equity value bridge, with dilution and double-count guards.

The same :class:`CapitalStructure` is used in both directions so the
intrinsic and market-implied calculations can never use inconsistent claims:

    equity = EV + excess cash + non-operating assets
             - debt - leases - pension deficit - preferred - minority
             - convertibles (if treated as debt) - expected contingent liabilities

    diluted shares = basic + RSUs + treasury-stock-method options
                     + conversion shares (if convertibles treated as equity)

Double-count guards (raise ``DoubleCountError``):

* lease liabilities given separately while ``debt_includes_leases`` is True;
* lease liabilities subtracted while the operating model's EBIT is already
  after lease cost (``ebit_after_lease_cost``): the obligation would be
  counted once in cash flows and again as a claim;
* convertibles can be debt *or* equity, never both (enforced by type).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class DoubleCountError(ValueError):
    pass


@dataclass(frozen=True)
class OptionTranche:
    count: float
    strike: float


@dataclass(frozen=True)
class CapitalStructure:
    basic_shares: float
    cash_and_investments: float = 0.0
    operating_cash_requirement: float = 0.0   # cash tied up in operations (not excess)
    non_operating_assets: float = 0.0         # equity stakes, idle real estate...
    total_debt: float = 0.0
    debt_includes_leases: bool = False
    lease_liabilities: float = 0.0
    ebit_after_lease_cost: bool = True        # True under US GAAP operating-lease accounting
    pension_deficit_after_tax: float = 0.0
    preferred_equity: float = 0.0
    minority_interest: float = 0.0
    convertible_face_value: float = 0.0
    convertible_treatment: Literal["debt", "equity"] = "debt"
    convertible_conversion_shares: float = 0.0
    contingent_liabilities_expected: float = 0.0
    rsus: float = 0.0
    options: tuple[OptionTranche, ...] = ()

    def validate(self) -> None:
        if self.basic_shares <= 0:
            raise ValueError("basic_shares must be positive")
        if self.debt_includes_leases and self.lease_liabilities:
            raise DoubleCountError("lease liabilities given separately but debt already includes leases")
        if self.lease_liabilities and self.ebit_after_lease_cost:
            raise DoubleCountError(
                "lease liabilities subtracted as a claim while EBIT is already after lease "
                "cost; either capitalise leases in EBIT or do not subtract them")
        if self.operating_cash_requirement > self.cash_and_investments:
            raise ValueError("operating cash requirement exceeds total cash")

    @property
    def excess_cash(self) -> float:
        return self.cash_and_investments - self.operating_cash_requirement

    def claims_ledger(self) -> list[tuple[str, float]]:
        """Signed adjustments from EV to equity value, in display order."""
        items = [
            ("excess cash", +self.excess_cash),
            ("non-operating assets", +self.non_operating_assets),
            ("debt" + (" (incl. leases)" if self.debt_includes_leases else ""), -self.total_debt),
            ("lease liabilities", -self.lease_liabilities),
            ("pension deficit (after tax)", -self.pension_deficit_after_tax),
            ("preferred equity", -self.preferred_equity),
            ("minority interest", -self.minority_interest),
            ("convertibles as debt",
             -self.convertible_face_value if self.convertible_treatment == "debt" else 0.0),
            ("expected contingent liabilities", -self.contingent_liabilities_expected),
        ]
        return [(k, v) for k, v in items if v]

    @property
    def net_adjustment(self) -> float:
        return sum(v for _, v in self.claims_ledger())

    def diluted_shares(self, share_price: float) -> float:
        """Treasury stock method at ``share_price`` (use the market price, stated as-of)."""
        shares = self.basic_shares + self.rsus
        for tr in self.options:
            if share_price > tr.strike:
                shares += tr.count * (1.0 - tr.strike / share_price)
        if self.convertible_treatment == "equity":
            shares += self.convertible_conversion_shares
        return shares


@dataclass(frozen=True)
class BridgeResult:
    enterprise_value: float
    ledger: tuple[tuple[str, float], ...]
    equity_value: float
    diluted_shares: float
    value_per_share: float
    notes: tuple[str, ...] = field(default_factory=tuple)


def equity_from_enterprise(ev: float, cap: CapitalStructure, dilution_price: float) -> BridgeResult:
    cap.validate()
    ledger = tuple(cap.claims_ledger())
    equity = ev + sum(v for _, v in ledger)
    shares = cap.diluted_shares(dilution_price)
    notes = [f"options diluted by treasury stock method at {dilution_price:,.2f}"] if cap.options else []
    if equity <= 0:
        notes.append("claims exceed enterprise value: common equity has no residual value in this case")
    per_share = max(equity, 0.0) / shares
    return BridgeResult(ev, ledger, equity, shares, per_share, tuple(notes))


def market_enterprise_value(share_price: float, cap: CapitalStructure) -> BridgeResult:
    """Market-implied EV from the share price, using the same claims as the DCF."""
    cap.validate()
    shares = cap.diluted_shares(share_price)
    market_cap = share_price * shares
    ledger = tuple(cap.claims_ledger())
    ev = market_cap - sum(v for _, v in ledger)
    return BridgeResult(ev, ledger, market_cap, shares, share_price)
