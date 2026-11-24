"""DEEPTERMINAL API (FastAPI). OpenAPI docs at /api/docs."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from deepterminal.data.sec_edgar import UnsupportedFiler

from .config import get_settings
from .research.orchestrator import recover_stale_jobs
from .services.gateway import DataUnavailable

STATUS_CODES = {"not_found": 404, "blocked": 503, "denied": 502, "rate_limited": 429, "offline": 503,
                "not_configured": 422, "unsupported": 422, "error": 502, "no_price": 422, "demo_readonly": 403}

# Public demo: the only requests that may change anything. Valuation calls are stateless
# calculations; chat and Thesis Challenger runs are rule-based and limited per client.
DEMO_WRITES = [
    (re.compile(r"^/api/companies/\d+/valuation(/shock)?$"), None),
    (re.compile(r"^/api/valuation/(sotp|nav)$"), None),
    (re.compile(r"^/api/chat/sessions$"), "chat"),
    (re.compile(r"^/api/chat/sessions/[0-9a-f]{32}/messages$"), "chat"),
    (re.compile(r"^/api/jobs$"), "jobs"),
]
# Public demo: responses computed only from the fixed snapshot, cached after the first request.
DEMO_CACHEABLE = re.compile(r"^/api/(companies/\d+(/(modules/[a-z_]+|risk-diff|time-machine|statements|filings(/[\w-]+)?"
                            r"|insiders|events|graph|peers|prices|search))?|companies|modules|macro|sources|compare)$")
DEMO_CACHE_MAX = 3000
DEMO_READONLY = ("Not available in the public demo, which serves a fixed snapshot read-only. "
                 "Run DEEPTERMINAL locally (free) for this feature.")


def create_app() -> FastAPI:
    s = get_settings()
    # The network-level cost guard (deepterminal.costpolicy) reads the environment; keep it in step
    # with settings loaded from .env so a .env opt-in is not silently ignored (or the reverse).
    os.environ["DEEPTERMINAL_ALLOW_PAID_APIS"] = "true" if s.allow_paid_apis else "false"
    os.environ["DEEPTERMINAL_NETWORK_DISABLED"] = "true" if s.public_demo else "false"
    logging.basicConfig(level=s.log_level, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    @asynccontextmanager
    async def lifespan(_app):
        n = recover_stale_jobs()
        if n:
            logging.getLogger("deepterminal").warning("marked %d stale jobs as failed", n)
        yield

    app = FastAPI(lifespan=lifespan, title="DEEPTERMINAL API", version="0.3.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
                  description="Evidence-first equity research API. All financial figures carry provenance; "
                              "unavailable data is reported, never invented.")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])
    hits: dict[str, deque] = defaultdict(deque)
    demo_hits: dict[tuple[str, str], deque] = defaultdict(deque)
    demo_cache: dict[str, tuple[bytes, str]] = {}
    if s.public_demo and s.demo_responses_path and os.path.exists(s.demo_responses_path):
        # Responses recorded from the same snapshot when it was built: the demo is fast from the first visit.
        with gzip.open(s.demo_responses_path, "rt") as f:
            demo_cache.update({k: (body.encode(), media) for k, (media, body) in json.load(f).items()
                               if DEMO_CACHEABLE.match(k.split("?", 1)[0])})

    def client_key(request: Request) -> str:
        if s.proxy_hops:
            hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
            if hops:
                return hops[-s.proxy_hops] if len(hops) >= s.proxy_hops else hops[0]
        return request.client.host if request.client else "local"

    def over_limit(q: deque, window: float, limit: int) -> bool:
        t = time.monotonic()
        while q and t - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(t)
        return False

    def prune(d: dict) -> None:
        if len(d) > 20_000:                       # many distinct clients: drop idle entries
            for k in [k for k, q in d.items() if not q]:
                del d[k]

    @app.middleware("http")
    async def security(request: Request, call_next):
        path = request.url.path
        if int(request.headers.get("content-length") or 0) > s.max_request_bytes:
            return JSONResponse({"detail": "request too large", "status": "unsupported"}, status_code=413)
        if s.public_demo and request.method not in ("GET", "HEAD", "OPTIONS"):
            rule = next((kind for rx, kind in DEMO_WRITES if rx.match(path)), False)
            if rule is False:
                return JSONResponse({"detail": DEMO_READONLY, "status": "demo_readonly", "message": DEMO_READONLY},
                                    status_code=403)
            if rule:
                limit = s.demo_chat_per_hour if rule == "chat" else s.demo_jobs_per_hour
                prune(demo_hits)
                if (over_limit(demo_hits[("*", "all")], 3600, s.demo_global_per_hour)
                        or over_limit(demo_hits[(client_key(request), rule)], 3600, limit)):
                    msg = f"Public demo limit reached ({limit} per hour for this feature). Try again later."
                    return JSONResponse({"detail": msg, "status": "rate_limited", "message": msg}, status_code=429,
                                        headers={"Retry-After": "600"})
        if s.api_token and path.startswith("/api") and path not in ("/api/health",) \
                and request.headers.get("authorization") != f"Bearer {s.api_token}":
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        if path.startswith("/api") and path != "/api/health":
            prune(hits)
            if over_limit(hits[client_key(request)], 60, s.rate_limit_per_minute):
                return JSONResponse({"detail": "rate limit exceeded", "status": "rate_limited"}, status_code=429,
                                    headers={"Retry-After": "30"})
        cache_key = None
        if s.public_demo and request.method == "GET" and DEMO_CACHEABLE.match(path):
            cache_key = f"{path}?{request.url.query}"
            hit = demo_cache.get(cache_key)
            if hit:
                return Response(hit[0], media_type=hit[1], headers={"X-Content-Type-Options": "nosniff",
                                                                    "Referrer-Policy": "no-referrer", "X-Demo-Cache": "hit"})
        start = time.perf_counter()
        resp = await call_next(request)
        if cache_key and resp.status_code == 200 and len(demo_cache) < DEMO_CACHE_MAX:
            body = b"".join([chunk async for chunk in resp.body_iterator])
            demo_cache[cache_key] = (body, resp.media_type or resp.headers.get("content-type", "application/json"))
            resp = Response(body, status_code=200, media_type=demo_cache[cache_key][1])
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        logging.getLogger("deepterminal.http").info("%s %s %s %.0fms", request.method, path, resp.status_code,
                                                    (time.perf_counter() - start) * 1000)
        return resp

    @app.exception_handler(DataUnavailable)
    async def unavailable_handler(_, e: DataUnavailable):
        return JSONResponse({"detail": e.message, **e.to_dict()}, status_code=STATUS_CODES.get(e.status, 503))

    @app.exception_handler(UnsupportedFiler)
    async def unsupported_handler(_, e: UnsupportedFiler):
        return JSONResponse({"detail": str(e), "status": "unsupported", "message": str(e)}, status_code=422)

    from .routers import companies, research, system, valuation, workspace
    for r in (system.router, companies.router, valuation.router, research.router, workspace.router):
        app.include_router(r, prefix="/api")

    return app


app = create_app()
