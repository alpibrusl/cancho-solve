#!/usr/bin/env python3
"""Benchmark of the sparse revised dual simplex (docs/design.md section 18.4): `solve run --relax --method dense|sparse` against OR-Tools' GLOP and CLP and HiGHS's dual simplex
(through scipy) on the families of section 18.1 and on min-cost flow LPs too large for the dense tableau. Same measurement rules as scripts/bench_ortools.py:
ours = whole process minus the minimum of `solve check` on the same model (start-up, reading, checking), minimum of RUNS; OR-Tools = `Solve()` alone after the model is built,
presolve and every option at its default; HiGHS = `highs-ds` in-process. One thread each. Every optimal value is held against the others to 1e-6 relative.
Needs ortools, scipy, numpy (a virtualenv). Usage: bench_sparse.py [--runs N] [--only SUBSTRING] [--skip-ortools]"""
import argparse, json, os, platform, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import highs
import subprocess
from ortools.linear_solver import pywraplp
import ortools

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--only", default="")
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")

families = [
    ("random dense LP", [(lambda s, m=m, n=n: lpgen.random_lp(s, m, n, 0.5), f"{m}x{n}") for m, n in [(200, 400), (400, 800), (800, 1600)]]),
    ("transportation", [(lambda s, a=a, b=b: lpgen.transportation(s, a, b), f"{a}x{b}") for a, b in [(40, 80), (80, 160), (100, 160)]]),
    ("assignment", [(lambda s, k=k: lpgen.assignment(s, k), f"{k}x{k}") for k in [40, 80, 100, 128]]),
    ("multi-knapsack", [(lambda s, n=n, k=k: lpgen.mkp(s, n, k), f"{n} items, {k} rows") for n, k in [(1000, 50), (2000, 100), (4000, 200)]]),
    ("min-cost flow", [(lambda s, n=n, a=a: lpgen.mincost_flow(s, n, a), f"{n} nodes, {a} arcs") for n, a in [(500, 4000), (1000, 8000), (2000, 16000), (4000, 16000), (8000, 16000)]]),
]

def run(method, verb, text):
    t = time.perf_counter()
    p = subprocess.run([SOLVE, *verb, *(["--method", method] if method else [])], input=text, capture_output=True, text=True)
    return p, time.perf_counter() - t

def ortools_lp(model, name):
    s = pywraplp.Solver.CreateSolver(name)
    inf = s.infinity()
    xs = [s.NumVar(v["lo"], v["hi"], v["name"]) for v in model["variables"]]
    for row in model["constraints"]:
        lo, hi = (-inf, row["rhs"]) if row["sense"] == "<=" else (row["rhs"], inf) if row["sense"] == ">=" else (row["rhs"], row["rhs"])
        c = s.Constraint(lo, hi)
        for j, a in row["terms"]:
            c.SetCoefficient(xs[j], a)
    o = s.Objective()
    for j, a in model["objective"]["terms"]:
        o.SetCoefficient(xs[j], a)
    o.SetOffset(model["objective"]["constant"])
    o.SetMaximization() if model["objective"]["sense"] == "maximize" else o.SetMinimization()
    return s, o

def timed(model, name, runs):
    best, val = None, None
    for _ in range(runs):
        s, o = ortools_lp(model, name)
        t = time.perf_counter()
        st = s.Solve()
        dt = time.perf_counter() - t
        if st != pywraplp.Solver.OPTIMAL:
            return None, None
        best = dt if best is None else min(best, dt)
        val = o.Value()
    return best, val

def best(f, runs):
    return min(f() for _ in range(runs))

print(f"machine: {platform.platform()}, {platform.machine()}; python {platform.python_version()}; runs: minimum of {args.runs}; ortools {ortools.__version__}; ours: {SOLVE}")
head = ["family", "size", "rows", "cols", "dense iters", "sparse iters", "refact.", "dense (s)", "sparse (s)", "GLOP (s)", "CLP (s)", "HiGHS (s)", "sparse/dense", "sparse/GLOP", "sparse/CLP", "sparse/HiGHS", "answer"]
rows = []
for family, sizes in families:
    for make, label in sizes:
        if args.only and args.only not in f"{family} {label}":
            continue
        text = make(7)
        p, _ = run(None, ["expand"], text)
        if p.returncode != 0:
            print("expand refused", family, label, p.stderr[:100])
            continue
        model = json.loads(p.stdout)
        m, n = len(model["constraints"]), len(model["variables"])
        floor = best(lambda: run(None, ["check"], text)[1], args.runs)
        d, _ = run("dense", ["run", "--relax"], text)
        s, _ = run("sparse", ["run", "--relax"], text)
        dgot = json.loads(d.stdout) if d.returncode in (0, 1) else None
        sgot = json.loads(s.stdout)
        if dgot is not None:
            dt = max(best(lambda: run("dense", ["run", "--relax"], text)[1], args.runs) - floor, 1e-4)
        else:
            dt = None
        st = max(best(lambda: run("sparse", ["run", "--relax"], text)[1], args.runs) - floor, 1e-4)
        g, gv = timed(model, "GLOP", args.runs)
        c, cv = timed(model, "CLP", args.runs)
        hs = highs(model, "highs-ds")
        h = best(lambda: highs(model, "highs-ds")[2], args.runs)
        vals = [gv, cv, hs[1]] + ([dgot["objective"]] if dgot else [])
        agree = sgot["status"] == "optimal" and all(v is not None and abs(sgot["objective"] - v) <= 1e-6 * (1 + abs(v)) for v in vals) and sgot["verified"]
        rows.append([family, label, str(m), str(n), str(dgot["stats"]["iterations"]) if dgot else "refused", str(sgot["stats"]["iterations"]), str(sgot["stats"].get("refactorisations", "")),
                     f"{dt:.4f}" if dt else "-", f"{st:.4f}", f"{g:.4f}", f"{c:.4f}", f"{h:.4f}", f"{st / dt:.2f}" if dt else "-", f"{st / g:.1f}", f"{st / c:.1f}", f"{st / h:.1f}", "ok" if agree else "DISAGREES"])
        print("  ".join(rows[-1]), flush=True)
table = [head] + rows
widths = [max(len(r[i]) for r in table) for i in range(len(head))]
print()
for r in table:
    print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
