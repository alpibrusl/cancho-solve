#!/usr/bin/env python3
"""Benchmark (docs/design.md section 14): `solve run --relax` against HiGHS on the same instances.
ours:  wall clock of the whole process `solve run --relax` (reads the model, expands it, solves, prints), minimum of RUNS; and the same minus the minimum of RUNS
       of `solve check` on the same model (start-up, read and expansion, no solve), which is the figure compared with HiGHS's in-process call.
highs: wall clock of scipy.optimize.linprog only, minimum of RUNS, for `highs-ds` (dual simplex) and `highs` (its default choice).
Usage: bench_highs.py [--runs N] [--markdown] [--max-seconds S]   (an instance of ours that takes longer than S seconds stops the family at that size)"""
import argparse, json, os, platform, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve, highs, violation

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=5)
ap.add_argument("--markdown", action="store_true")
ap.add_argument("--max-seconds", type=float, default=60.0)
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")

families = [
    ("random dense LP", [(lambda s, m=m, n=n: lpgen.random_lp(s, m, n, 0.5), f"{m}x{n}") for m, n in [(20, 40), (50, 100), (100, 200), (200, 400), (400, 800), (800, 1600)]]),
    ("transportation", [(lambda s, a=a, b=b: lpgen.transportation(s, a, b), f"{a}x{b}") for a, b in [(10, 20), (40, 80), (60, 120), (80, 160), (100, 160)]]),
    ("assignment (LP relaxation)", [(lambda s, k=k: lpgen.assignment(s, k), f"{k}x{k}") for k in [20, 40, 60, 80, 100]]),
    ("multi-knapsack (relaxation)", [(lambda s, n=n, k=k: lpgen.mkp(s, n, k), f"{n} items, {k} rows") for n, k in [(100, 10), (500, 30), (1000, 50), (2000, 100), (4000, 200)]]),
]

def best(f, runs):
    return min(f() for _ in range(runs))

rows = []
for family, sizes in families:
    for make, label in sizes:
        text = make(7)
        p, _ = run_solve(SOLVE, ["expand"], text)
        if p.returncode != 0:
            print("expand refused", family, label, p.stderr[:200], file=sys.stderr)
            continue
        model = json.loads(p.stdout)
        m, n = len(model["constraints"]), len(model["variables"])
        q, t0 = run_solve(SOLVE, ["run", "--relax"], text)
        if q.returncode not in (0, 1):
            rows.append((family, label, m, n, None, None, None, None, None, None, f"refused: {json.loads(q.stderr)['error']}"))
            continue
        got = json.loads(q.stdout)
        ours = best(lambda: run_solve(SOLVE, ["run", "--relax"], text)[1], args.runs)
        floor = best(lambda: run_solve(SOLVE, ["check"], text)[1], args.runs)
        hs = {}
        for meth in ("highs-ds", "highs"):
            hs[meth] = best(lambda: highs(model, meth)[2], args.runs)
        _, hobj, _, hit = highs(model, "highs-ds")
        agree = got["status"] == "optimal" and abs(got["objective"] - hobj) <= 1e-6 * (1 + abs(hobj))
        rows.append((family, label, m, n, got["stats"]["iterations"], ours, max(ours - floor, 1e-4), hs["highs-ds"], hs["highs"], hit, "ok" if agree else f"DISAGREES ({got['status']} {got.get('objective')} vs {hobj})"))
        if ours > args.max_seconds:
            break

print(f"machine: {platform.platform()}, {platform.machine()}; python {platform.python_version()}; runs: minimum of {args.runs}")
import scipy
print(f"HiGHS through scipy {scipy.__version__} linprog; ours: {SOLVE}")
head = ["family", "size", "rows", "cols", "our iters", "HiGHS iters", "ours total (s)", "ours - floor (s)", "HiGHS dual (s)", "HiGHS default (s)", "ours/dual", "ours/default", "answer"]
def fmt(r):
    f, l, m, n, it, o, os_, d, h, hit, ans = r
    if o is None:
        return [f, l, str(m), str(n), "-", "-", "-", "-", "-", "-", "-", "-", ans]
    return [f, l, str(m), str(n), str(it), str(hit), f"{o:.4f}", f"{os_:.4f}", f"{d:.4f}", f"{h:.4f}", f"{os_ / d:.1f}", f"{os_ / h:.1f}", ans]
table = [head] + [fmt(r) for r in rows]
if args.markdown:
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for r in table[1:]:
        print("| " + " | ".join(r) + " |")
else:
    widths = [max(len(r[i]) for r in table) for i in range(len(head))]
    for r in table:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
