#!/usr/bin/env python3
"""Where the time of the sparse LP solver goes (docs/design.md section 22): iterations of ours against HiGHS (dual simplex, scipy) and GLOP / CLP (OR-Tools, default presolve),
and the time per iteration divided by the rows. Instances: the ample EV-depot LP at three sizes, a transportation LP and a min-cost flow LP.
Usage: SOLVE=build/solve [METHOD=sparse-raw] python scripts/profile_lp.py [--runs N] [only]"""
import argparse, json, os, subprocess, sys, time
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from ortools.linear_solver import pywraplp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lpgen
from evgen import generate
ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("only", nargs="?", default=None)
args = ap.parse_args()
only = args.only
SOLVE = os.environ.get("SOLVE", "build/solve")
METHOD = os.environ.get("METHOD", "sparse")   # sparse (with the presolve of design.md 21.3) or sparse-raw


def run(argv, text):
    t = time.perf_counter()
    p = subprocess.run([SOLVE] + argv, input=text, capture_output=True, text=True)
    return p, time.perf_counter() - t


def ours(text):
    floor = min(run(["check"], text)[1] for _ in range(args.runs))
    best, st = None, None
    for _ in range(args.runs):
        p, dt = run(["run", "--relax", "--method", METHOD], text)
        o = json.loads(p.stdout)
        best = dt if best is None else min(best, dt)
        st = o["stats"]
        val = o["objective"]
    return max(best - floor, 1e-4), st, val


def highs(model):
    n = len(model["variables"])
    c = np.zeros(n)
    for j, a in model["objective"]["terms"]:
        c[j] += a
    ri, ci, vv, bu, bl, ru = [], [], [], [], [], []
    for r, row in enumerate(model["constraints"]):
        for j, a in row["terms"]:
            ri.append(r); ci.append(j); vv.append(a)
    A = coo_matrix((vv, (ri, ci)), shape=(len(model["constraints"]), n)).tocsr()
    rows = model["constraints"]
    ub_rows = [i for i, r in enumerate(rows) if r["sense"] == "<="]
    lb_rows = [i for i, r in enumerate(rows) if r["sense"] == ">="]
    eq_rows = [i for i, r in enumerate(rows) if r["sense"] == "=="]
    import scipy.sparse as sps
    Aub = sps.vstack([A[ub_rows], -A[lb_rows]]) if (ub_rows or lb_rows) else None
    bub = np.array([rows[i]["rhs"] for i in ub_rows] + [-rows[i]["rhs"] for i in lb_rows])
    Aeq = A[eq_rows] if eq_rows else None
    beq = np.array([rows[i]["rhs"] for i in eq_rows]) if eq_rows else None
    bounds = [(v["lo"], v["hi"]) for v in model["variables"]]
    best = None
    for _ in range(args.runs):
        t = time.perf_counter()
        r = linprog(c, A_ub=Aub, b_ub=bub if Aub is not None else None, A_eq=Aeq, b_eq=beq, bounds=bounds, method="highs-ds")
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
    return best, r.nit, r.fun + model["objective"]["constant"]


def ortools(model, name):
    best, it = None, None
    for _ in range(args.runs):
        s = pywraplp.Solver.CreateSolver(name)
        inf = s.infinity()
        xs = [s.NumVar(v["lo"], v["hi"], "") for v in model["variables"]]
        for row in model["constraints"]:
            lo, hi = (-inf, row["rhs"]) if row["sense"] == "<=" else (row["rhs"], inf) if row["sense"] == ">=" else (row["rhs"], row["rhs"])
            cn = s.Constraint(lo, hi)
            for j, a in row["terms"]:
                cn.SetCoefficient(xs[j], a)
        o = s.Objective()
        for j, a in model["objective"]["terms"]:
            o.SetCoefficient(xs[j], a)
        o.SetOffset(model["objective"]["constant"])
        o.SetMinimization() if model["objective"]["sense"] == "minimize" else o.SetMaximization()
        t = time.perf_counter()
        s.Solve()
        dt = time.perf_counter() - t
        best = dt if best is None else min(best, dt)
        it = s.iterations()
    return best, it


INST = [("ev ample 48x24", lambda: generate(48, 24, "ample", 7)), ("ev ample 96x32", lambda: generate(96, 32, "ample", 7)), ("ev ample 144x40", lambda: generate(144, 40, "ample", 7)),
        ("transportation 100x160", lambda: lpgen.transportation(7, 100, 160)), ("min-cost flow 2000n 16000a", lambda: lpgen.mincost_flow(7, 2000, 16000)),
        ("min-cost flow 8000n 16000a", lambda: lpgen.mincost_flow(7, 8000, 16000))]
print(f"{'instance':28} {'rows':>6} {'cols':>6} | {'ours it':>7} {'refac':>5} {'s':>7} {'us/it':>7} {'ns/it/row':>9} | {'HiGHS it':>8} {'s':>7} | {'GLOP it':>7} {'s':>7} | {'CLP it':>7} {'s':>7}")
for name, gen in INST:
    if only and only not in name:
        continue
    text = gen()
    p, _ = run(["expand"], text)
    model = json.loads(p.stdout)
    t, st, val = ours(text)
    ht, hit, hv = highs(model)
    gt, git = ortools(model, "GLOP")
    ct, cit = ortools(model, "CLP")
    assert abs(hv - val) <= 1e-6 * (1 + abs(hv)), (name, hv, val)
    print(f"{name:28} {st['rows']:6d} {st['columns']:6d} | {st['iterations']:7d} {st['refactorisations']:5d} {t:7.4f} {1e6*t/st['iterations']:7.1f} {1e9*t/st['iterations']/st['rows']:9.1f} | {hit:8d} {ht:7.4f} | {git:7d} {gt:7.4f} | {cit:7d} {ct:7.4f}")
