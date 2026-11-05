#!/usr/bin/env python3
"""Benchmark (docs/design.md section 18): `solve run --relax` against OR-Tools' LP solvers (GLOP, CLP) on the same instances as scripts/bench_highs.py.
Needs the `ortools` package (a virtualenv: python3 -m venv V && V/bin/pip install ortools scipy numpy), and HiGHS through scipy for the third column.
ours:   whole process `solve run --relax` minus the minimum of `solve check` on the same model (start-up, read, expansion), minimum of RUNS.
OR-Tools: wall clock of `solver.Solve()` only through pywraplp (the model is built before the clock starts), minimum of RUNS; presolve and every option at its default.
Usage: bench_ortools.py [--runs N] [--max-seconds S] [--sizes small|all]"""
import argparse, json, os, platform, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve, highs
from ortools.linear_solver import pywraplp
import ortools

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--max-seconds", type=float, default=60.0)
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")

families = [
    ("random dense LP", [(lambda s, m=m, n=n: lpgen.random_lp(s, m, n, 0.5), f"{m}x{n}") for m, n in [(100, 200), (200, 400), (400, 800), (800, 1600)]]),
    ("transportation", [(lambda s, a=a, b=b: lpgen.transportation(s, a, b), f"{a}x{b}") for a, b in [(40, 80), (80, 160), (100, 160)]]),
    ("assignment (LP relaxation)", [(lambda s, k=k: lpgen.assignment(s, k), f"{k}x{k}") for k in [40, 80, 100]]),
    ("multi-knapsack (relaxation)", [(lambda s, n=n, k=k: lpgen.mkp(s, n, k), f"{n} items, {k} rows") for n, k in [(500, 30), (1000, 50), (2000, 100), (4000, 200)]]),
]

def ortools_lp(model, name):
    s = pywraplp.Solver.CreateSolver(name)
    inf = s.infinity()
    xs = [s.NumVar(v["lo"], v["hi"], v["name"]) for v in model["variables"]]
    for row in model["constraints"]:
        lo, hi = (-inf, row["rhs"]) if row["sense"] == "<=" else (row["rhs"], inf) if row["sense"] == ">=" else (row["rhs"], row["rhs"])
        c = s.Constraint(lo, hi)
        for j, a in row["terms"]:
            c.SetCoefficient(xs[j], a)
    obj = model["objective"]
    o = s.Objective()
    for j, a in obj["terms"]:
        o.SetCoefficient(xs[j], a)
    o.SetOffset(obj["constant"])
    o.SetMaximization() if obj["sense"] == "maximize" else o.SetMinimization()
    return s, o

def timed(model, name, runs):
    best, val, it = None, None, None
    for _ in range(runs):
        s, o = ortools_lp(model, name)
        t = time.perf_counter()
        st = s.Solve()
        dt = time.perf_counter() - t
        if st != pywraplp.Solver.OPTIMAL:
            return None, None, None
        best = dt if best is None else min(best, dt)
        val, it = o.Value(), s.iterations()
    return best, val, it

def best(f, runs):
    return min(f() for _ in range(runs))

print(f"machine: {platform.platform()}, {platform.machine()}; python {platform.python_version()}; runs: minimum of {args.runs}; ortools {ortools.__version__}; ours: {SOLVE}")
head = ["family", "size", "rows", "cols", "our iters", "GLOP iters", "ours-floor (s)", "GLOP (s)", "CLP (s)", "HiGHS (s)", "ours/GLOP", "ours/CLP", "ours/HiGHS", "answer"]
rows = []
for family, sizes in families:
    for make, label in sizes:
        text = make(7)
        p, _ = run_solve(SOLVE, ["expand"], text)
        if p.returncode != 0:
            continue
        model = json.loads(p.stdout)
        m, n = len(model["constraints"]), len(model["variables"])
        q, _ = run_solve(SOLVE, ["run", "--relax"], text)
        got = json.loads(q.stdout)
        ours = best(lambda: run_solve(SOLVE, ["run", "--relax"], text)[1], args.runs)
        floor = best(lambda: run_solve(SOLVE, ["check"], text)[1], args.runs)
        ours = max(ours - floor, 1e-4)
        g, gv, git = timed(model, "GLOP", args.runs)
        c, cv, _ = timed(model, "CLP", args.runs)
        h = best(lambda: highs(model, "highs-ds")[2], args.runs)
        agree = all(v is not None and abs(got["objective"] - v) <= 1e-6 * (1 + abs(v)) for v in (gv, cv)) and got["status"] == "optimal"
        rows.append([family, label, str(m), str(n), str(got["stats"]["iterations"]), str(git), f"{ours:.4f}", f"{g:.4f}", f"{c:.4f}", f"{h:.4f}", f"{ours / g:.1f}", f"{ours / c:.1f}", f"{ours / h:.1f}", "ok" if agree else "DISAGREES"])
        if ours > args.max_seconds:
            break
table = [head] + rows
widths = [max(len(r[i]) for r in table) for i in range(len(head))]
for r in table:
    print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
