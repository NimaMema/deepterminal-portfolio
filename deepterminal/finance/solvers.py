"""Robust scalar root finding for reverse-DCF problems.

A reverse DCF must never pretend a solution is unique when it is not (for
example, when ROIC < cost of capital more growth *destroys* value, so the
value function is not monotonic). :func:`find_roots` scans the interval for
every sign change and refines each one with bisection, so callers can report
zero, one or several solutions honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RootScan:
    roots: list[float]
    lower: float
    upper: float
    min_value: float     # min of f over the scan grid (diagnostic)
    max_value: float     # max of f over the scan grid (diagnostic)
    monotonic: bool      # f was monotonic over the scan grid


def bisect(f: Callable[[float], float], lo: float, hi: float,
           tol: float = 1e-10, max_iter: int = 300) -> float:
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise ValueError("bisect requires a sign change on [lo, hi]")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if fm == 0 or (hi - lo) < tol:
            return mid
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def find_roots(f: Callable[[float], float], lower: float, upper: float,
               samples: int = 200, tol: float = 1e-10) -> RootScan:
    if upper <= lower:
        raise ValueError("upper must exceed lower")
    xs = [lower + (upper - lower) * i / samples for i in range(samples + 1)]
    ys = []
    for x in xs:
        try:
            ys.append(f(x))
        except ValueError:          # e.g. invalid region (rate <= growth)
            ys.append(float("nan"))
    roots: list[float] = []
    for (x0, y0), (x1, y1) in zip(zip(xs, ys), zip(xs[1:], ys[1:])):
        if y0 != y0 or y1 != y1:    # NaN guard
            continue
        if y0 == 0:
            roots.append(x0)
        elif (y0 > 0) != (y1 > 0) and y1 != 0:
            roots.append(bisect(f, x0, x1, tol=tol))
    if ys and ys[-1] == 0:
        roots.append(xs[-1])
    finite = [y for y in ys if y == y]
    diffs = [b - a for a, b in zip(finite, finite[1:])]
    monotonic = all(d >= 0 for d in diffs) or all(d <= 0 for d in diffs)
    dedup: list[float] = []
    for r in roots:
        if not dedup or abs(r - dedup[-1]) > max(tol * 10, 1e-9):
            dedup.append(r)
    return RootScan(dedup, lower, upper,
                    min(finite) if finite else float("nan"),
                    max(finite) if finite else float("nan"), monotonic)
