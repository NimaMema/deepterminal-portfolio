"""SYNTHETIC SEC companyfacts generator for tests.

Produces data in the exact shape of data.sec.gov/api/xbrl/companyfacts for a
FICTIONAL company. Every number is invented. It reproduces real filing
structure: 10-K comparatives, 10-Q 3-month and YTD facts, cash-flow facts
reported only year-to-date, cover-page share counts, and one restatement.
"""

from datetime import date, timedelta

M = 1e6
FY_REV = {2021: 1000, 2022: 1100, 2023: 1210, 2024: 1300, 2025: 1400}
ORIGINAL_FY2023_REV = 1150          # restated to 1210 in the FY2024 10-K
Q_REV = {(2025, 1): 330, (2025, 2): 340, (2025, 3): 350, (2026, 1): 360, (2026, 2): 375}
TEN_K_FILED = {y: date(y + 1, 2, 15) for y in FY_REV}
TEN_Q_FILED = {(y, q): date(y, 3 * q, 28) + timedelta(days=37) for (y, q) in Q_REV}
RATIOS = {"OperatingIncomeLoss": 0.20, "NetIncomeLoss": 0.15,
          "NetCashProvidedByUsedInOperatingActivities": 0.18,
          "PaymentsToAcquirePropertyPlantAndEquipment": 0.06,
          "DepreciationDepletionAndAmortization": 0.04, "ShareBasedCompensation": 0.01,
          "GrossProfit": 0.45, "InterestExpense": 0.01,
          "IncomeTaxExpenseBenefit": 0.15 / 0.8 * 0.2,
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": 0.15 / 0.8}
CASH_FLOW = {"NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
             "DepreciationDepletionAndAmortization", "ShareBasedCompensation"}
INSTANTS = {"CashAndCashEquivalentsAtCarryingValue": 200, "MarketableSecuritiesCurrent": 50,
            "LongTermDebt": 300, "StockholdersEquity": 900, "Assets": 1500,
            "LiabilitiesAndStockholdersEquity": 1500, "AccountsReceivableNetCurrent": 150,
            "InventoryNet": 100, "AccountsPayableCurrent": 80, "MinorityInterest": 10,
            "OperatingLeaseLiability": 40}


def _accn(filed: date, n: int) -> str:
    return f"0000000000-{filed.year % 100:02d}-{n:06d}"


def q_end(y: int, q: int) -> date:
    return date(y, 3 * q + 1, 1) - timedelta(days=1) if q < 4 else date(y, 12, 31)


def build(cik: int = 0, name: str = "SYNTHETIC QUARTERLY CO (fictional)") -> dict:
    facts: dict[str, list] = {}
    shares: list = []
    dei_shares: list = []

    def add(concept, start, end, val, filed, accn, form, unit="USD"):
        d = {"end": end.isoformat(), "val": val, "filed": filed.isoformat(), "accn": accn, "form": form,
             "fy": filed.year, "fp": "FY" if form == "10-K" else "Q"}
        if start:
            d["start"] = start.isoformat()
        (shares if unit == "shares" else facts.setdefault(concept, [])).append(d)

    n = 0
    for fy, filed in TEN_K_FILED.items():
        n += 1
        accn = _accn(filed, n)
        for y in (fy, fy - 1, fy - 2):          # current + two comparative years
            if y not in FY_REV:
                continue
            rev = ORIGINAL_FY2023_REV if (y == 2023 and fy == 2023) else FY_REV[y]
            s, e = date(y, 1, 1), date(y, 12, 31)
            add("Revenues", s, e, rev * M, filed, accn, "10-K")
            for c, r in RATIOS.items():
                add(c, s, e, rev * r * M, filed, accn, "10-K")
            add("WeightedAverageNumberOfDilutedSharesOutstanding", s, e, 100 * M, filed, accn, "10-K", "shares")
        for y in (fy, fy - 1):
            if y in FY_REV:
                for c, v in INSTANTS.items():
                    add(c, None, date(y, 12, 31), v * M, filed, accn, "10-K")
        dei_shares.append({"end": (filed - timedelta(days=5)).isoformat(), "val": 99 * M,
                           "filed": filed.isoformat(), "accn": accn, "form": "10-K"})
    for (y, q), filed in TEN_Q_FILED.items():
        n += 1
        accn = _accn(filed, n)
        e = q_end(y, q)
        s3 = date(y, 3 * q - 2, 1)
        ytd = sum(Q_REV[(y, k)] for k in range(1, q + 1))
        rev = Q_REV[(y, q)]
        add("Revenues", s3, e, rev * M, filed, accn, "10-Q")
        if q > 1:
            add("Revenues", date(y, 1, 1), e, ytd * M, filed, accn, "10-Q")
        for c, r in RATIOS.items():
            if c not in CASH_FLOW:
                add(c, s3, e, rev * r * M, filed, accn, "10-Q")
            add(c, date(y, 1, 1), e, ytd * r * M, filed, accn, "10-Q") if (c in CASH_FLOW or q > 1) else None
        add("WeightedAverageNumberOfDilutedSharesOutstanding", s3, e, 100 * M, filed, accn, "10-Q", "shares")
        for c, v in INSTANTS.items():
            add(c, None, e, v * M, filed, accn, "10-Q")
        dei_shares.append({"end": (filed - timedelta(days=5)).isoformat(), "val": 99 * M,
                           "filed": filed.isoformat(), "accn": accn, "form": "10-Q"})
    usgaap = {c: {"label": c, "units": {"USD": v}} for c, v in facts.items()}
    usgaap["WeightedAverageNumberOfDilutedSharesOutstanding"] = {"units": {"shares": shares}}
    return {"cik": cik, "entityName": name, "_comment": "SYNTHETIC test data; numbers are invented",
            "facts": {"us-gaap": usgaap,
                      "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": dei_shares}}}}}


TICKERS = {"0": {"cik_str": 0, "ticker": "SYNQ", "title": "SYNTHETIC QUARTERLY CO (fictional)"},
           "1": {"cik_str": 1, "ticker": "BRK-B", "title": "SYNTHETIC CLASS B HOLDER (fictional)"}}
SUBMISSIONS = {"cik": "0", "name": "SYNTHETIC QUARTERLY CO (fictional)", "tickers": ["SYNQ"], "sic": "3571",
               "sicDescription": "Electronic Computers (synthetic)", "fiscalYearEnd": "1231",
               "exchanges": ["SYNTHETIC"],
               "filings": {"recent": {"accessionNumber": ["0000000000-26-000010", "0000000000-26-000005"],
                                      "form": ["10-Q", "10-K"], "filingDate": ["2026-08-04", "2026-02-15"],
                                      "reportDate": ["2026-06-30", "2025-12-31"],
                                      "primaryDocument": ["q2.htm", "k.htm"]}}}
