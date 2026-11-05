#!/usr/bin/env python3
"""Gate (docs/design.md section 21.2, written before the hypersparse code): the time of one iteration of the sparse dual simplex must not grow with the number of rows.
Model: the ample EV-depot LP (scripts/evgen.py, seed 7) at 48 x 24 (2,400 rows) and 144 x 40 (11,744 rows), `solve run --relax --method sparse`. Time = the process minus the
minimum of `solve check` on the same text, minimum of RUNS; per iteration = divided by the iterations of the answer. Requires time/iteration (large) <= BOUND * time/iteration (small);
BOUND = 3.0 against a ratio of 4.9 in rows (measured 4.06 to 4.28 before the fix, 2.2 after). Both answers must be optimal and agree with HiGHS (scipy) to 1e-6 relative.
Usage: SOLVE=build/solve python3 scripts/check_speed.py [--runs N] [--bound X]   (needs scipy for the oracle)"""
import argparse, json, os, subprocess, sys, time
import numpy as np
from scipy.optimize import linprog
import scipy.sparse as sps
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=5)
ap.add_argument("--bound", type=float, default=3.0)
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")


def run(argv, text):
    t = time.perf_counter()
    p = subprocess.run([SOLVE] + argv, input=text, capture_output=True, text=True)
    return p, time.perf_counter() - t


def highs(model):
    n = len(model["variables"])
    c = np.zeros(n)
    for j, a in model["objective"]["terms"]:
        c[j] += a
    rows = model["constraints"]
    ri, ci, vv = [], [], []
    for r, row in enumerate(rows):
        for j, a in row["terms"]:
            ri.append(r); ci.append(j); vv.append(a)
    A = sps.coo_matrix((vv, (ri, ci)), shape=(len(rows), n)).tocsr()
    ub = [i for i, r in enumerate(rows) if r["sense"] == "<="]
    lb = [i for i, r in enumerate(rows) if r["sense"] == ">="]
    eq = [i for i, r in enumerate(rows) if r["sense"] == "=="]
    Aub = sps.vstack([A[ub], -A[lb]]) if ub or lb else None
    bub = np.array([rows[i]["rhs"] for i in ub] + [-rows[i]["rhs"] for i in lb])
    r = linprog(c, A_ub=Aub, b_ub=bub if Aub is not None else None, A_eq=A[eq] if eq else None, b_eq=np.array([rows[i]["rhs"] for i in eq]) if eq else None,
                bounds=[(v["lo"], v["hi"]) for v in model["variables"]], method="highs-ds")
    return r.fun + model["objective"]["constant"]


def measure(V, T):
    text = generate(V, T, "ample", 7)
    floor = min(run(["check"], text)[1] for _ in range(args.runs))
    best, out = None, None
    for _ in range(args.runs):
        p, dt = run(["run", "--relax", "--method", "sparse"], text)
        out = json.loads(p.stdout)
        if out.get("status") != "optimal":
            print(f"FAIL {V}x{T}: status {out.get('status')}")
            sys.exit(1)
        best = dt if best is None else min(best, dt)
    ref = highs(json.loads(run(["expand"], text)[0].stdout))
    if abs(ref - out["objective"]) > 1e-6 * (1 + abs(ref)):
        print(f"FAIL {V}x{T}: objective {out['objective']} against HiGHS {ref}")
        sys.exit(1)
    it, rows = out["stats"]["iterations"], out["stats"]["rows"]
    return max(best - floor, 1e-5) / it, it, rows, best - floor


(a, ia, ra, ta), (b, ib, rb, tb) = measure(48, 24), measure(144, 40)
ratio = b / a
print(f"48 x 24: {ra} rows, {ia} iterations, {ta:.4f} s, {a * 1e6:.1f} us/iteration;  144 x 40: {rb} rows, {ib} iterations, {tb:.4f} s, {b * 1e6:.1f} us/iteration;  "
      f"ratio {ratio:.2f} (rows {rb / ra:.2f}), bound {args.bound}")
if ratio > args.bound:
    print("FAIL: the time per iteration grows with the number of rows")
    sys.exit(1)
print("ok")
