"""Flatten figure provenance into rows for the report, dashboard and CSV export."""

from __future__ import annotations

import csv
import io

from ..data.case_file import Case

FLOW_FIELDS = ("revenue", "operating_income", "net_income", "operating_cash_flow", "capex",
               "depreciation", "stock_based_comp", "diluted_shares")
STOCK_FIELDS = ("cash", "total_debt", "shareholders_equity", "accounts_receivable", "inventory")
COLUMNS = ("figure", "period", "value", "unit", "concept", "form", "accession", "filed",
           "retrieved_at", "derivation", "derivation_inputs", "source_url")


def provenance_rows(case: Case) -> list[dict[str, str]]:
    rows = []
    periods = list(case.history) + ([case.ttm] if case.ttm else [])
    for p in periods:
        label = f"FY{p.fiscal_year}" if p.period_type == "FY" else f"{p.period_type} to {p.period_end}"
        for name in FLOW_FIELDS + STOCK_FIELDS:
            prov = p.provenance.get(name)
            if prov:
                rows.append(_row(f"{label} {name}", prov))
    for prov in case.figure_provenance:
        rows.append(_row(f"{prov.field} (valuation input)", prov))
    return rows


def _row(figure: str, prov) -> dict[str, str]:
    period = f"{prov.period_start}–{prov.period_end}" if prov.period_start else f"at {prov.period_end}"
    unit = "USD m" if prov.unit == "USD" else ("m shares" if prov.unit == "shares" else prov.unit)
    return {"figure": figure, "period": period, "value": f"{prov.value:,.3f}", "unit": unit,
            "concept": prov.concept, "form": prov.form, "accession": prov.accession,
            "filed": str(prov.filed), "retrieved_at": prov.retrieved_at.isoformat() if prov.retrieved_at else "",
            "derivation": prov.derivation,
            "derivation_inputs": " | ".join(f"{i.form} {i.accession} ({i.period_start}–{i.period_end})"
                                            for i in prov.inputs),
            "source_url": prov.source_url}


def provenance_csv(case: Case) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(provenance_rows(case))
    return buf.getvalue()
