"""Record the values the deployed demo must reproduce:  python make_expected.py http://127.0.0.1:7860"""
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")


def call(path, body=None):
    req = urllib.request.Request(base + "/api" + path, data=json.dumps(body).encode() if body else None,
                                 headers={"content-type": "application/json"}, method="POST" if body else "GET")
    return json.load(urllib.request.urlopen(req, timeout=120))


out = []
for c in call("/companies"):
    prices = call(f"/companies/{c['id']}/prices")
    if not prices:
        continue
    req = {"settings": {"discount_rate": 0.09}, "as_of": prices[0]["as_of"]}
    r = call(f"/companies/{c['id']}/valuation", req)
    base_ps = next(s["per_share"] for s in r["scenarios"] if s["name"] == "base")
    rd = next((x for x in r.get("reverse_dcf") or [] if x["lever"] == "initial_growth_fading"), None)
    out.append({"company_id": c["id"], "ticker": c["ticker"], "request": req, "base_per_share": base_ps,
                "implied_growth": rd["solutions"][0]["value"] if rd and rd.get("solutions") else None,
                "verdict": (r.get("assessment") or {}).get("verdict")})
json.dump({"valuations": out}, open("expected.json", "w"), indent=2)
print(json.dumps(out, indent=1))
