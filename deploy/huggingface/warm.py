"""Warm the public demo's response cache: compute every module and screen once at startup, so
visitors never wait for a first computation. Runs in the background; failures are only logged.
With DEEPTERMINAL_WARM_OUT=<file.json.gz> it also records the responses, which are shipped with the
snapshot and preloaded by the API (DEEPTERMINAL_DEMO_RESPONSES), so a restarted Space is fast at once."""
import gzip
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = os.environ.get("DEEPTERMINAL_WARM_API", "http://127.0.0.1:8000/api")
WARM_FLAG = os.environ.get("DEEPTERMINAL_WARM_FLAG", "/tmp/deepterminal-warm-done")


RECORDED: dict[str, list[str]] = {}            # cache key -> [media type, body], for --out


def get(path: str):
    try:
        with urllib.request.urlopen(API + path, timeout=600) as r:
            body = r.read()
            path_only, _, query = path.partition("?")
            RECORDED[f"/api{path_only}?{query}"] = [r.headers.get_content_type(), body.decode()]
            return json.loads(body)
    except Exception as e:                   # noqa: BLE001 - best effort
        print(f"warm: {path}: {e}", flush=True)
        return None


for _ in range(120):
    if get("/health"):
        break
    time.sleep(1)
t = time.time()
modules = [m["key"] for m in get("/modules") or []]
paths = ["/companies", "/macro", "/sources"]
for c in get("/companies") or []:
    i = c["id"]
    paths += [f"/companies/{i}", f"/companies/{i}/statements", f"/companies/{i}/filings?limit=400", f"/companies/{i}/insiders",
              f"/companies/{i}/events", f"/companies/{i}/graph", f"/companies/{i}/peers", f"/companies/{i}/prices",
              f"/companies/{i}/risk-diff"] + [f"/companies/{i}/modules/{m}" for m in modules]
with ThreadPoolExecutor(2) as ex:
    list(ex.map(get, paths))
print(f"warm: {len(paths)} responses cached in {time.time() - t:.0f}s", flush=True)
OUT = os.environ.get("DEEPTERMINAL_WARM_OUT")    # record the responses to ship with the snapshot
if OUT:
    with gzip.open(OUT, "wt") as f:
        json.dump({k: v for k, v in RECORDED.items() if not k.startswith("/api/health")}, f)
    print(f"warm: recorded {len(RECORDED)} responses to {OUT}", flush=True)
open(WARM_FLAG, "w").write(f"{len(paths)} responses in {time.time() - t:.0f}s\n")
