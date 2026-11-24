"""SYNTHETIC demo dataset in exact SEC EDGAR formats.

Every company, number and document produced here is FICTIONAL and labelled as
such in its name ("(Demo)"), in every document header, and by the
``synthetic`` flag the API propagates to the UI. It exists so the full
application can be developed, tested and demonstrated where SEC EDGAR is not
reachable. It is never mixed with live data (``DEEPTERMINAL_DATA_MODE=demo``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

M = 1e6
BANNER = "SYNTHETIC DEMO DOCUMENT — FICTIONAL COMPANY — NOT REAL SEC DATA"


@dataclass
class DemoCo:
    cik: int
    ticker: str
    name: str
    sic: str
    sic_desc: str
    state: str
    rev0: float                    # FY2015 revenue, $m
    growth: list[float]            # FY2016..FY2025
    op_margin: list[float]         # FY2015..FY2025
    gross_margin: float
    rnd_pct: float
    capex_pct: float
    da_pct: float
    sbc_pct: float
    ar_days: float
    inv_days: float
    ap_days: float
    deferred_pct: float
    rpo_mult: float
    shares0: float                 # millions
    share_growth: float            # per year (negative = buybacks)
    payout: float                  # dividends / net income
    debt: float
    cash0: float
    goodwill: float
    q_growth_2026: float
    suppliers: list[tuple[str, str, str]] = field(default_factory=list)   # (name, country, what)
    customers: list[tuple[str, float]] = field(default_factory=list)      # (descriptor, share)
    subsidiaries: list[tuple[str, str]] = field(default_factory=list)
    executives: list[tuple[str, str, int, int]] = field(default_factory=list)  # name, title, salary k, total k
    risks: dict[int, list[tuple[str, str]]] = field(default_factory=dict)      # first FY → [(heading, body)]
    outlook: dict[int, str] = field(default_factory=dict)
    legal: str = "We are not currently a party to any material pending legal proceedings."
    former_names: list[dict] = field(default_factory=list)
    restate_fy: int | None = None
    restate_factor: float = 1.0
    eightk: list[tuple[str, str, str]] = field(default_factory=list)       # (date, items, headline)
    insiders: list[tuple[str, str, str, str, float, float]] = field(default_factory=list)  # date,name,role,code,shares,price
    buzzwords: dict[int, int] = field(default_factory=dict)              # FY → mentions of "artificial intelligence"
    going_concern: bool = False
    sourcing_notes: dict[int, str] = field(default_factory=dict)        # FY (and later) → supply mitigation text


def _companies() -> list[DemoCo]:
    return [
        DemoCo(
            cik=9900001, ticker="DQD", name="Demo Quantum Devices Inc. (Demo)", sic="3674",
            sic_desc="Semiconductors & Related Devices", state="DE",
            rev0=1800, growth=[.12, .18, .22, .08, .15, .35, .28, .05, .55, .62],
            op_margin=[.14, .15, .17, .19, .13, .17, .24, .27, .18, .33, .41],
            gross_margin=.58, rnd_pct=.17, capex_pct=.05, da_pct=.04, sbc_pct=.06,
            ar_days=48, inv_days=95, ap_days=40, deferred_pct=.02, rpo_mult=.3,
            shares0=2400, share_growth=.004, payout=.05, debt=4000, cash0=2500, goodwill=1500,
            q_growth_2026=.09,
            sourcing_notes={2025: "We are qualifying a second foundry for our mature-node products; qualification of an "
                                  "alternative source for advanced nodes would take several years."},
            suppliers=[("Formosa Precision Foundry Co., Ltd.", "Taiwan", "wafer fabrication (sole source for advanced nodes)"),
                       ("Keystone Substrate Corporation", "Japan", "advanced packaging substrates"),
                       ("Pacific Memory Holdings Ltd.", "South Korea", "high-bandwidth memory"),
                       ("Lumen Assembly Services Inc.", "Malaysia", "assembly and test")],
            customers=[("a hyperscale cloud provider", .19), ("a second cloud provider", .13)],
            subsidiaries=[("DQD Technologies Ltd.", "Israel"), ("Demo Quantum Devices B.V.", "Netherlands"),
                          ("DQD Semiconductor (Shanghai) Co., Ltd.", "China"), ("DQD International Holdings LLC", "Delaware")],
            executives=[("Avery Lindqvist", "Chief Executive Officer and Co-Founder", 1000, 31500),
                        ("Morgan Achebe", "Chief Financial Officer", 850, 12400),
                        ("Riley Okafor", "Executive Vice President, Operations", 700, 9800)],
            risks={2015: [("Dependence on third-party foundries",
                           "We rely on a limited number of third-party foundries to manufacture our products, and the loss of a foundry could disrupt supply."),
                          ("Competition", "The semiconductor industry is intensely competitive and characterised by rapid technological change.")],
                   2021: [("Concentration of customers", "A small number of customers account for a significant portion of our revenue.")],
                   2023: [("Export controls", "New export control regulations restrict sales of certain advanced products to customers in China and may reduce our revenue."),
                          ("Single-source supply of advanced nodes", "We depend on a single foundry located in Taiwan for all of our most advanced products; geopolitical tension or natural disasters could materially disrupt supply.")],
                   2025: [("Demand volatility in AI infrastructure", "Recent demand has been driven by investment in artificial intelligence infrastructure, which may not be sustained; customers may reduce orders or develop in-house alternatives.")]},
            outlook={2021: "We expect revenue growth to continue as data-center adoption expands.",
                     2023: "We expect revenue to grow significantly in fiscal 2024 driven by data-center demand, and we will expand supply capacity.",
                     2024: "We expect strong growth to continue in fiscal 2025; supply remains constrained for our newest products.",
                     2025: "We anticipate demand to exceed supply through the first half of fiscal 2026 and expect gross margins to remain near current levels."},
            legal="We are subject to a putative securities class action filed in 2024 alleging misstatements about cryptocurrency-mining demand; we believe the claims lack merit.",
            restate_fy=2023, restate_factor=.985,
            eightk=[("2024-02-21", "2.02,9.01", "Results of operations for fiscal 2023"),
                    ("2024-05-02", "5.02", "Departure of Chief Accounting Officer"),
                    ("2025-02-20", "2.02,9.01", "Results of operations for fiscal 2024"),
                    ("2025-08-14", "1.01", "Entry into long-term capacity agreement with foundry partner"),
                    ("2026-02-19", "2.02,9.01", "Results of operations for fiscal 2025")],
            insiders=[("2025-03-12", "Avery Lindqvist", "CEO, Director", "S", 240000, 118.4),
                      ("2025-06-10", "Avery Lindqvist", "CEO, Director", "S", 260000, 131.9),
                      ("2025-09-15", "Morgan Achebe", "CFO", "S", 45000, 140.2),
                      ("2025-11-20", "Riley Okafor", "EVP Operations", "S", 30000, 151.0),
                      ("2026-03-05", "Jordan Pike", "Director", "P", 5000, 128.5)],
            buzzwords={2019: 2, 2020: 4, 2021: 9, 2022: 15, 2023: 41, 2024: 88, 2025: 132}),
        DemoCo(
            cik=9900002, ticker="DHB", name="Demo Harbor Beverages Co. (Demo)", sic="2086",
            sic_desc="Bottled & Canned Soft Drinks", state="DE",
            rev0=9000, growth=[.02, .03, .01, .03, -.04, .07, .05, .04, .03, .03],
            op_margin=[.27, .27, .28, .28, .27, .26, .27, .28, .28, .29, .29],
            gross_margin=.60, rnd_pct=0, capex_pct=.04, da_pct=.035, sbc_pct=.01,
            ar_days=32, inv_days=70, ap_days=60, deferred_pct=0, rpo_mult=0,
            shares0=1300, share_growth=-.008, payout=.70, debt=12000, cash0=3000, goodwill=7000,
            q_growth_2026=.03,
            suppliers=[("Granite Aluminum Can Corp.", "United States", "aluminum cans"),
                       ("Tropic Sugar Refiners S.A.", "Brazil", "sweeteners")],
            customers=[("a national grocery chain", .08)],
            subsidiaries=[("Harbor Bottling LLC", "Delaware"), ("Harbor Beverages Mexico S. de R.L.", "Mexico")],
            executives=[("Casey Brennan", "Chairman and Chief Executive Officer", 1500, 18200),
                        ("Devon Marsh", "Chief Financial Officer", 900, 7100)],
            risks={2015: [("Commodity costs", "Increases in the cost of aluminum, sweeteners and energy could reduce our margins."),
                          ("Consumer preferences", "Changes in consumer preferences toward lower-sugar products could reduce demand.")],
                   2022: [("Inflation", "Elevated inflation may reduce consumer demand and increase our costs.")]},
            outlook={2022: "We expect organic revenue growth of 4% to 5% in fiscal 2023.",
                     2023: "We expect organic revenue growth of 3% to 4% in fiscal 2024.",
                     2024: "We expect organic revenue growth of 3% to 4% in fiscal 2025.",
                     2025: "We expect organic revenue growth of 3% in fiscal 2026."},
            eightk=[("2025-02-11", "2.02,9.01", "Results of operations for fiscal 2024"),
                    ("2026-02-10", "2.02,9.01", "Results of operations for fiscal 2025")],
            insiders=[("2025-05-02", "Casey Brennan", "CEO, Chairman", "S", 50000, 61.2),
                      ("2025-08-20", "Taylor Quinn", "Director", "P", 8000, 58.9)],
            buzzwords={2023: 1, 2024: 2, 2025: 3}),
        DemoCo(
            cik=9900003, ticker="DIM", name="Demo Ironworks Machinery Corp. (Demo)", sic="3531",
            sic_desc="Construction Machinery & Equip", state="DE",
            rev0=40000, growth=[-.05, .18, .20, .02, -.22, .22, .16, .13, -.03, -.04],
            op_margin=[.08, .06, .12, .15, .15, .10, .13, .14, .20, .19, .17],
            gross_margin=.30, rnd_pct=.04, capex_pct=.03, da_pct=.04, sbc_pct=.004,
            ar_days=60, inv_days=120, ap_days=55, deferred_pct=.03, rpo_mult=.6,
            shares0=590, share_growth=-.015, payout=.30, debt=27000, cash0=7000, goodwill=6000,
            q_growth_2026=-.02,
            suppliers=[("Midland Steel Works Inc.", "United States", "steel plate"),
                       ("Rhine Hydraulics GmbH", "Germany", "hydraulic components"),
                       ("Shenzhen Power Electronics Co., Ltd.", "China", "engine control electronics")],
            subsidiaries=[("Ironworks Financial Services Corp.", "Delaware"), ("Ironworks Brasil Ltda.", "Brazil")],
            executives=[("Jamie Ortega", "Chief Executive Officer", 1600, 24000),
                        ("Sam Whitfield", "Chief Financial Officer", 950, 8900)],
            risks={2015: [("Cyclical demand", "Demand for our products is highly cyclical and depends on construction, mining and energy activity."),
                          ("Steel prices", "Increases in steel prices could reduce our margins.")],
                   2018: [("Tariffs", "Tariffs on steel and on components imported from China increase our costs.")]},
            outlook={2023: "We expect sales to be broadly flat in 2024 with continued strong price realization.",
                     2024: "We expect lower sales in 2025 as dealers reduce inventory.",
                     2025: "We expect sales to be slightly lower in 2026."},
            eightk=[("2025-01-30", "2.02,9.01", "Results of operations for fiscal 2024"),
                    ("2026-01-29", "2.02,9.01", "Results of operations for fiscal 2025")],
            insiders=[("2025-04-29", "Jamie Ortega", "CEO", "S", 40000, 330.0)],
            buzzwords={2024: 3, 2025: 5}),
        DemoCo(
            cik=9900004, ticker="DCS", name="Demo Cloudline Software Inc. (Demo)", sic="7372",
            sic_desc="Services-Prepackaged Software", state="DE",
            rev0=600, growth=[.38, .35, .33, .30, .29, .26, .22, .19, .17, .15],
            op_margin=[-.22, -.18, -.12, -.09, -.06, -.03, .01, .04, .08, .11, .14],
            gross_margin=.76, rnd_pct=.24, capex_pct=.03, da_pct=.03, sbc_pct=.17,
            ar_days=70, inv_days=0, ap_days=20, deferred_pct=.42, rpo_mult=1.6,
            shares0=180, share_growth=.03, payout=0, debt=1500, cash0=1200, goodwill=800,
            q_growth_2026=.035,
            suppliers=[("Stratus Hosting Services LLC", "United States", "cloud infrastructure hosting")],
            customers=[],
            subsidiaries=[("Cloudline Software UK Ltd.", "United Kingdom"), ("Cloudline Software India Pvt. Ltd.", "India")],
            executives=[("Quinn Halvorsen", "Chief Executive Officer", 600, 22000),
                        ("Rowan Petit", "Chief Financial Officer", 520, 9400)],
            risks={2015: [("History of losses", "We have a history of losses and may not achieve or sustain profitability."),
                          ("Competition", "The market for our software is competitive.")],
                   2024: [("AI-native competitors", "New competitors using generative AI could offer similar functionality at lower prices.")]},
            outlook={2023: "We expect revenue growth of approximately 18% and further operating margin expansion in fiscal 2024.",
                     2024: "We expect revenue growth of approximately 16% in fiscal 2025.",
                     2025: "We expect revenue growth of approximately 14% in fiscal 2026."},
            eightk=[("2025-03-04", "2.02,9.01", "Results of operations for fiscal 2024"),
                    ("2025-10-01", "4.01", "Change in registrant's certifying accountant"),
                    ("2026-03-03", "2.02,9.01", "Results of operations for fiscal 2025")],
            insiders=[("2025-06-01", "Quinn Halvorsen", "CEO", "S", 60000, 210.0),
                      ("2025-12-01", "Rowan Petit", "CFO", "S", 15000, 228.0)],
            buzzwords={2022: 3, 2023: 18, 2024: 44, 2025: 61},
            former_names=[{"name": "Cloudline Systems Inc. (Demo)", "from": "2010-01-01", "to": "2017-06-30"}]),
        DemoCo(
            cik=9900005, ticker="DNR", name="Demo Northfield Retail Corp. (Demo)", sic="5311",
            sic_desc="Retail-Department Stores", state="OH",
            rev0=12000, growth=[-.02, -.04, -.03, -.05, -.18, .06, -.04, -.07, -.08, -.10],
            op_margin=[.05, .04, .03, .02, .01, -.06, .01, -.01, -.02, -.04, -.06],
            gross_margin=.34, rnd_pct=0, capex_pct=.02, da_pct=.03, sbc_pct=.004,
            ar_days=8, inv_days=110, ap_days=45, deferred_pct=0, rpo_mult=0,
            shares0=300, share_growth=.02, payout=.2, debt=3800, cash0=900, goodwill=0,
            q_growth_2026=-.09,
            suppliers=[("Orient Apparel Sourcing Ltd.", "Vietnam", "private-label apparel")],
            subsidiaries=[("Northfield Stores LLC", "Ohio")],
            executives=[("Blake Harrow", "Chief Executive Officer", 1100, 6400)],
            risks={2015: [("Competition from online retailers", "Competition from e-commerce retailers may reduce our sales.")],
                   2020: [("Liquidity", "Our liquidity could be constrained if sales continue to decline.")],
                   2025: [("Going concern", "Recurring losses and upcoming debt maturities raise substantial doubt about our ability to continue as a going concern.")]},
            outlook={2023: "We expect comparable sales to stabilize in fiscal 2024.",
                     2024: "We expect comparable sales to return to growth in the second half of fiscal 2025.",
                     2025: "We are evaluating strategic alternatives, including a potential restructuring of our debt."},
            eightk=[("2025-06-12", "5.02", "Departure of Chief Financial Officer"),
                    ("2026-04-02", "1.01,2.03", "Entry into amended credit agreement; creation of direct financial obligation")],
            insiders=[("2025-04-10", "Blake Harrow", "CEO", "P", 20000, 4.1)],
            going_concern=True),
    ]


# ───────────────────────────── financial model ─────────────────────────────

def _annual_model(c: DemoCo) -> dict[int, dict[str, float]]:
    years = list(range(2015, 2026))
    out: dict[int, dict[str, float]] = {}
    rev = c.rev0
    shares = c.shares0
    re_earn = c.cash0 * 0.8
    cash = c.cash0
    for i, y in enumerate(years):
        if i:
            rev *= 1 + c.growth[i - 1]
            shares *= 1 + c.share_growth
        om = c.op_margin[i]
        op = rev * om
        interest = c.debt * 0.045
        pretax = op - interest
        tax = max(pretax, 0) * 0.19
        ni = pretax - tax
        da = rev * c.da_pct
        sbc = rev * c.sbc_pct
        ocf = ni + da + sbc - rev * (c.growth[i - 1] if i else 0) * 0.08
        capex = rev * c.capex_pct
        div = max(ni, 0) * c.payout
        buyback = max(-c.share_growth, 0) * shares * 40
        cash = max(cash + ocf - capex - div - buyback, rev * 0.04)
        cogs = rev * (1 - c.gross_margin)
        ar = rev * c.ar_days / 365
        inv = cogs * c.inv_days / 365
        ap = cogs * c.ap_days / 365
        ppe = rev * (c.capex_pct * 4)
        deferred = rev * c.deferred_pct
        other_assets = rev * 0.15
        assets = cash + ar + inv + ppe + c.goodwill + other_assets
        other_liab = rev * 0.10
        cur_liab = ap + deferred + other_liab * 0.5 + c.debt * 0.08
        liabilities = ap + deferred + other_liab + c.debt + rev * 0.02
        equity = assets - liabilities
        re_earn += ni - div
        out[y] = dict(
            Revenues=rev, CostOfRevenue=cogs, GrossProfit=rev - cogs, OperatingIncomeLoss=op,
            NetIncomeLoss=ni, NetCashProvidedByUsedInOperatingActivities=ocf,
            PaymentsToAcquirePropertyPlantAndEquipment=capex, DepreciationDepletionAndAmortization=da,
            ShareBasedCompensation=sbc, InterestExpense=interest, IncomeTaxExpenseBenefit=tax,
            IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=pretax,
            SellingGeneralAndAdministrativeExpense=rev * (c.gross_margin - om - c.rnd_pct),
            ResearchAndDevelopmentExpense=rev * c.rnd_pct, PaymentsOfDividends=div,
            PaymentsForRepurchaseOfCommonStock=buyback,
            CashAndCashEquivalentsAtCarryingValue=cash, AccountsReceivableNetCurrent=ar, InventoryNet=inv,
            AccountsPayableCurrent=ap, Assets=assets, AssetsCurrent=cash + ar + inv + other_assets * 0.4,
            LiabilitiesCurrent=cur_liab, Liabilities=liabilities, LiabilitiesAndStockholdersEquity=assets,
            StockholdersEquity=equity, RetainedEarningsAccumulatedDeficit=re_earn, PropertyPlantAndEquipmentNet=ppe,
            Goodwill=c.goodwill, LongTermDebt=c.debt, ContractWithCustomerLiabilityCurrent=deferred,
            RevenueRemainingPerformanceObligation=rev * c.rpo_mult, OperatingLeaseLiability=rev * 0.03,
            WeightedAverageNumberOfDilutedSharesOutstanding=shares)
        out[y] = {k: v for k, v in out[y].items() if not (k in ("ContractWithCustomerLiabilityCurrent",
                                                                  "RevenueRemainingPerformanceObligation",
                                                                  "ResearchAndDevelopmentExpense", "InventoryNet")
                                                         and v == 0)}
    return out


FLOW = {"Revenues", "CostOfRevenue", "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss",
        "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
        "DepreciationDepletionAndAmortization", "ShareBasedCompensation", "InterestExpense",
        "IncomeTaxExpenseBenefit",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "SellingGeneralAndAdministrativeExpense", "ResearchAndDevelopmentExpense", "PaymentsOfDividends",
        "PaymentsForRepurchaseOfCommonStock", "WeightedAverageNumberOfDilutedSharesOutstanding"}
CASH_FLOW = {"NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
             "DepreciationDepletionAndAmortization", "ShareBasedCompensation", "PaymentsOfDividends",
             "PaymentsForRepurchaseOfCommonStock"}
QW = (0.24, 0.25, 0.25, 0.26)


def _accn(c: DemoCo, filed: date, n: int) -> str:
    return f"{c.cik:010d}-{filed.year % 100:02d}-{n:06d}"


@dataclass
class DemoFiling:
    accession: str
    form: str
    filed: date
    report_date: date | None
    primary_document: str
    items: str = ""
    documents: dict[str, str] = field(default_factory=dict)


def _q_end(y: int, q: int) -> date:
    return date(y, 3 * q + 1, 1) - timedelta(days=1) if q < 4 else date(y, 12, 31)


def build_company(c: DemoCo) -> tuple[dict, dict, list[DemoFiling]]:
    model = _annual_model(c)
    filings: list[DemoFiling] = []
    usgaap: dict[str, dict[str, list]] = {}
    dei: list = []
    n = 0

    def add(concept, start, end, val, filed, accn, form):
        unit = "shares" if concept.startswith("WeightedAverage") else "USD"
        scale = 1e6
        d = {"end": end.isoformat(), "val": round(val * scale), "filed": filed.isoformat(), "accn": accn,
             "form": form, "fy": filed.year, "fp": "FY" if form == "10-K" else "Q"}
        if start:
            d["start"] = start.isoformat()
        usgaap.setdefault(concept, {"label": concept, "units": {}})["units"].setdefault(unit, []).append(d)

    for fy in range(2015, 2026):
        filed = date(fy + 1, 2, 18) + timedelta(days=c.cik % 7)
        n += 1
        accn = _accn(c, filed, n)
        for y in (fy, fy - 1, fy - 2):
            if y not in model:
                continue
            factor = c.restate_factor if (c.restate_fy == y and fy == y) else 1.0
            for k, v in model[y].items():
                if k in FLOW:
                    add(k, date(y, 1, 1), date(y, 12, 31), v * (factor if k == "Revenues" else 1), filed, accn, "10-K")
        for y in (fy, fy - 1):
            if y in model:
                for k, v in model[y].items():
                    if k not in FLOW:
                        add(k, None, date(y, 12, 31), v, filed, accn, "10-K")
        dei.append({"end": (filed - timedelta(days=6)).isoformat(),
                    "val": round(model[fy]["WeightedAverageNumberOfDilutedSharesOutstanding"] * 0.985 * 1e6),
                    "filed": filed.isoformat(), "accn": accn, "form": "10-K"})
        docs = {"10k.htm": ten_k_html(c, fy, model), "ex21.htm": exhibit21_html(c, fy)}
        filings.append(DemoFiling(accn, "10-K", filed, date(fy, 12, 31), "10k.htm", "", docs))

    # Quarterly: FY2025 Q1–Q3 and FY2026 Q1–Q2
    q2026 = {k: v * (1 + c.q_growth_2026) for k, v in model[2025].items()}
    quarters = [(2025, 1, model[2025]), (2025, 2, model[2025]), (2025, 3, model[2025]),
                (2026, 1, q2026), (2026, 2, q2026)]
    for y, q, base in quarters:
        filed = _q_end(y, q) + timedelta(days=38)
        n += 1
        accn = _accn(c, filed, n)
        e = _q_end(y, q)
        s3 = date(y, 3 * q - 2, 1)
        for k, v in base.items():
            if k in FLOW:
                share = QW[q - 1] if k != "WeightedAverageNumberOfDilutedSharesOutstanding" else 1.0
                ytd = sum(QW[:q]) if k != "WeightedAverageNumberOfDilutedSharesOutstanding" else 1.0
                if k not in CASH_FLOW:
                    add(k, s3, e, v * share, filed, accn, "10-Q")
                if k in CASH_FLOW or q > 1:
                    add(k, date(y, 1, 1), e, v * ytd, filed, accn, "10-Q")
            else:
                add(k, None, e, v * (1 + (c.q_growth_2026 * q / 4 if y == 2026 else 0)), filed, accn, "10-Q")
        dei.append({"end": (filed - timedelta(days=5)).isoformat(),
                    "val": round(base["WeightedAverageNumberOfDilutedSharesOutstanding"] * 0.985 * 1e6),
                    "filed": filed.isoformat(), "accn": accn, "form": "10-Q"})
        filings.append(DemoFiling(accn, "10-Q", filed, e, "10q.htm", "",
                                  {"10q.htm": f"<html><body><p>{BANNER}</p><h1>{c.name} Form 10-Q for the quarter ended {e}</h1>"
                                              f"<p>Quarterly report. See XBRL financial data.</p></body></html>"}))

    for d, items, headline in c.eightk:
        filed = date.fromisoformat(d)
        n += 1
        accn = _accn(c, filed, n)
        filings.append(DemoFiling(accn, "8-K", filed, filed, "8k.htm", items,
                                  {"8k.htm": f"<html><body><p>{BANNER}</p><h1>{c.name} — Form 8-K</h1>"
                                             f"<p>Items {items}. {headline}.</p></body></html>"}))
    for d, name, role, code, shares, price in c.insiders:
        filed = date.fromisoformat(d) + timedelta(days=2)
        n += 1
        accn = _accn(c, filed, n)
        filings.append(DemoFiling(accn, "4", filed, date.fromisoformat(d), "form4.xml", "",
                                  {"form4.xml": form4_xml(c, d, name, role, code, shares, price)}))
    for fy in (2023, 2024, 2025):
        filed = date(fy + 1, 3, 25)
        n += 1
        accn = _accn(c, filed, n)
        filings.append(DemoFiling(accn, "DEF 14A", filed, None, "proxy.htm", "",
                                  {"proxy.htm": proxy_html(c, fy)}))

    facts = {"cik": c.cik, "entityName": c.name, "_comment": "SYNTHETIC demo data; fictional company",
             "facts": {"us-gaap": usgaap, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": dei}}}}}
    filings.sort(key=lambda f: f.filed, reverse=True)
    subs = {
        "cik": str(c.cik), "entityType": "operating", "sic": c.sic, "sicDescription": c.sic_desc,
        "name": c.name, "tickers": [c.ticker], "exchanges": ["DEMO"], "ein": "00-0000000",
        "category": "Large accelerated filer (demo)", "fiscalYearEnd": "1231",
        "stateOfIncorporation": c.state, "stateOfIncorporationDescription": c.state,
        "website": "", "formerNames": c.former_names, "_comment": "SYNTHETIC demo data",
        "addresses": {"business": {"street1": "1 Demo Plaza", "city": "Example City", "stateOrCountry": "CA",
                                   "zipCode": "00000"},
                      "mailing": {"street1": "PO Box 0", "city": "Example City", "stateOrCountry": "CA", "zipCode": "00000"}},
        "filings": {"recent": {
            "accessionNumber": [f.accession for f in filings], "filingDate": [f.filed.isoformat() for f in filings],
            "reportDate": [f.report_date.isoformat() if f.report_date else "" for f in filings],
            "form": [f.form for f in filings], "primaryDocument": [f.primary_document for f in filings],
            "items": [f.items for f in filings], "size": [sum(len(v) for v in f.documents.values()) for f in filings]}},
    }
    return facts, subs, filings


# ───────────────────────────── documents ─────────────────────────────

def _risks_for(c: DemoCo, fy: int) -> list[tuple[str, str]]:
    return [r for start, rs in sorted(c.risks.items()) if start <= fy for r in rs]


AI_SENTENCES = [
    "We continue to invest in artificial intelligence capabilities across our product portfolio.",
    "Customers are evaluating our products for artificial intelligence workloads.",
    "Our roadmap includes features designed for artificial intelligence applications.",
    "We believe artificial intelligence represents a significant long-term opportunity.",
]


def ten_k_html(c: DemoCo, fy: int, model: dict) -> str:
    sup = "".join(f"<p>We purchase {what} from {name}, located in {country}.</p>" for name, country, what in c.suppliers)
    note = next((t for y, t in sorted(c.sourcing_notes.items(), reverse=True) if fy >= y), "")
    sourcing = f"<p>{note}</p>" if note else ""
    cust = "".join(f"<p>Sales to {d} accounted for {s:.0%} of our total revenue in fiscal {fy}.</p>" for d, s in c.customers)
    ai = c.buzzwords.get(fy, 0)
    # The synthetic 10-K is a few hundred words, so mentions are scaled down to keep intensity in a realistic range.
    ai_text = " ".join(AI_SENTENCES[i % len(AI_SENTENCES)] for i in range(round(ai / 10) if ai >= 5 else min(ai, 1)))
    risks = "".join(f"<p><b>{h}.</b> {b}</p>" for h, b in _risks_for(c, fy))
    outlook = c.outlook.get(fy, "We do not provide a quantitative outlook.")
    gc = ("<p>Our recurring losses and upcoming maturities raise substantial doubt about our ability to continue as a going concern.</p>"
          if c.going_concern and fy >= 2025 else "")
    acct = ("<p>We adopted ASU 2023-07, Segment Reporting, effective for fiscal 2024.</p>" if fy == 2024 else "")
    rev = model[fy]["Revenues"]
    return f"""<html><body><p>{BANNER}</p>
<h1>{c.name} — Annual Report on Form 10-K for the fiscal year ended December 31, {fy}</h1>
<p>TABLE OF CONTENTS Item 1. Business Item 1A. Risk Factors Item 3. Legal Proceedings Item 7. Management's Discussion and Analysis</p>
<h2>Item 1. Business</h2>
<p>{c.name} is a fictional company used to demonstrate DEEPTERMINAL. It operates in {c.sic_desc.lower()}.</p>
<p>Manufacturing and suppliers.</p>{sup}{sourcing}{cust}<p>{ai_text}</p>
<h2>Item 1A. Risk Factors</h2>{risks}
<h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>
<h2>Item 3. Legal Proceedings</h2><p>{c.legal if fy >= 2024 else 'We are not currently a party to any material pending legal proceedings.'}</p>
<h2>Item 4. Mine Safety Disclosures</h2><p>Not applicable.</p>
<h2>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</h2>
<p>Revenue for fiscal {fy} was ${rev:,.0f} million.</p><p>Outlook. {outlook}</p>{gc}{acct}
<h2>Item 8. Financial Statements and Supplementary Data</h2><p>See the XBRL financial data.</p>
</body></html>"""


def exhibit21_html(c: DemoCo, fy: int) -> str:
    rows = "".join(f"<tr><td>{n}</td><td>{j}</td></tr>" for n, j in c.subsidiaries)
    return (f"<html><body><p>{BANNER}</p><h1>Exhibit 21 — Subsidiaries of {c.name}</h1>"
            f"<table><tr><th>Name</th><th>Jurisdiction</th></tr>{rows}</table></body></html>")


def proxy_html(c: DemoCo, fy: int) -> str:
    rows = "".join(f"<tr><td>{n}</td><td>{t}</td><td>{fy}</td><td>{s * 1000:,.0f}</td><td>{tot * 1000:,.0f}</td></tr>"
                   for n, t, s, tot in c.executives)
    bios = "".join(f"<p><b>{n}</b>, {t}. Fictional executive biography for demonstration.</p>" for n, t, _, _ in c.executives)
    return (f"<html><body><p>{BANNER}</p><h1>{c.name} — Proxy Statement (DEF 14A) for the {fy + 1} annual meeting</h1>"
            f"<h2>Executive Officers</h2>{bios}"
            f"<h2>Summary Compensation Table</h2><table><tr><th>Name</th><th>Principal Position</th><th>Year</th>"
            f"<th>Salary ($)</th><th>Total ($)</th></tr>{rows}</table>"
            f"<h2>Board Independence</h2><p>Seven of our nine directors are independent.</p></body></html>")


def form4_xml(c: DemoCo, d: str, name: str, role: str, code: str, shares: float, price: float) -> str:
    ad = "D" if code == "S" else "A"
    return f"""<?xml version="1.0"?>
<!-- {BANNER} -->
<ownershipDocument>
  <documentType>4</documentType>
  <periodOfReport>{d}</periodOfReport>
  <issuer><issuerCik>{c.cik:010d}</issuerCik><issuerName>{c.name}</issuerName><issuerTradingSymbol>{c.ticker}</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>{name}</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>{1 if 'Director' in role else 0}</isDirector><isOfficer>{1 if role != 'Director' else 0}</isOfficer><officerTitle>{role}</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>{d}</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares:.0f}</value></transactionShares>
        <transactionPricePerShare><value>{price}</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>{shares * 9:.0f}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


@lru_cache
def dataset() -> dict[int, tuple[DemoCo, dict, dict, list[DemoFiling]]]:
    out = {}
    for c in _companies():
        facts, subs, filings = build_company(c)
        out[c.cik] = (c, facts, subs, filings)
    return out


def tickers_json() -> dict:
    return {str(i): {"cik_str": cik, "ticker": c.ticker, "title": c.name}
            for i, (cik, (c, _, _, _)) in enumerate(dataset().items())}


if __name__ == "__main__":   # quick inspection
    for cik, (c, facts, subs, filings) in dataset().items():
        print(c.ticker, len(json.dumps(facts)) // 1024, "KB facts,", len(filings), "filings")
