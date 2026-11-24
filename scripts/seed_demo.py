"""Seed a running DEEPTERMINAL API (demo mode) with the five fictional companies, labelled synthetic
prices and one investigation each, so every screen has content.

    python scripts/seed_demo.py [--api http://127.0.0.1:8000]

Refuses to run against an API that is not in demo mode: it never writes synthetic prices next to real data.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import httpx

# Fictional prices for fictional companies; stored with an explicit "synthetic" source label.
DEMO_PRICES = {"DQD": 140.0, "DHB": 26.0, "DIM": 240.0, "DCS": 33.0, "DNR": 4.1}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--no-jobs", action="store_true", help="skip running investigations")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.api.rstrip("/") + "/api", timeout=120)
    if c.get("/status").json().get("data_mode") != "demo":
        print("API is not in demo mode; refusing to seed synthetic prices.", file=sys.stderr)
        return 1
    as_of = (date.today() - timedelta(days=1)).isoformat()
    jobs = []
    for ticker, px in DEMO_PRICES.items():
        co = c.get(f"/companies/resolve/{ticker}").raise_for_status().json()
        if not c.get(f"/companies/{co['id']}/prices").json():
            c.post(f"/companies/{co['id']}/prices",
                   json={"value": px, "as_of": as_of, "source": "demo closing price (synthetic)"}).raise_for_status()
        if not a.no_jobs:
            jobs.append((ticker, c.post("/jobs", json={"company_id": co["id"], "kind": "investigation"}).raise_for_status().json()["id"]))
        print(f"{ticker}: company {co['id']}, price {px} (synthetic)")
    for ticker, jid in jobs:
        while (st := c.get(f"/jobs/{jid}").json()["status"]) in ("queued", "running"):
            time.sleep(1)
        print(f"{ticker}: investigation {st}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
