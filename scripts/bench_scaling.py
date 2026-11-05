#!/usr/bin/env python3
"""Benchmark (docs/design.md section 21): the EV-depot model of docs/examples/ev_depot.sol, grown, against OR-Tools (SCIP and CBC for the integer model, GLOP and CLP for its
relaxation) and HiGHS through scipy. The models are generated from a seed, written as .sol text for `solve`, and read back with `solve expand` for the other solvers, so no
solver is given a different model.

ours:     the wall time of `solve run [--relax]` minus the minimum of `solve check` on the same text (start-up, read, expansion); a run over LIMIT seconds is `limit`.
others:   the wall time of the solver call alone (the model is built before the clock starts); a time limit of LIMIT seconds, anything but optimal is `limit`.
runs:     the minimum of RUNS for a run under 5 s, a single run above it.
Every solver is given a relative MIP gap of 1e-9 (their defaults, 1e-4, stop at answers that our exact search would not call optimal: CBC returned 529.15 where the optimum is 529.12);
every optimal value is compared with HiGHS's to 1e-6 relative; a disagreement fails the script (exit 1).
Needs ortools and scipy: SP/venv-ortools/bin/python scripts/bench_scaling.py
Usage: bench_scaling.py [--runs N] [--limit S] [--max-v V] [--out PATH]   (writes PATH.txt and PATH.json, default docs/bench/scaling)"""
import argparse, json, math, os, platform, random, subprocess, sys, time
import numpy as np
from scipy.optimize import milp, linprog, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
from ortools.linear_solver import pywraplp
import ortools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=3)
ap.add_argument("--limit", type=float, default=90.0)
ap.add_argument("--max-v", type=int, default=1000)
ap.add_argument("--settings", default="tight,ample", help="comma-separated settings to run (the ample ladder is the LP-bound one)")
ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "bench", "scaling"))
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")
# the ladders end where the best solver needs 10 s or more (tight: HiGHS takes 21 s at 36 x 20, 18 s at 48 x 24 and more than 60 s at 72 x 28); the ample model is an LP with
# an integer link and every solver finishes it in milliseconds at any size the language holds (16,384 columns), so its ladder ends at the largest size that fits
SIZES = {"tight": [(12, 12), (24, 16), (36, 20), (48, 24), (60, 26)], "ample": [(48, 24), (96, 32), (144, 40)]}
PMAX = 11


def run_solve(argv, text, limit):
    t = time.perf_counter()
    try:
        p = subprocess.run([SOLVE] + argv, input=text, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return None, time.perf_counter() - t
    return p, time.perf_counter() - t


def ours(text, relax):
    argv = ["run", "--node-limit", "2000000"] + (["--relax"] if relax else [])   # the wall-clock limit, not the node limit, is what ends a run
    floor = min(run_solve(["check"], text, 60)[1] for _ in range(args.runs))
    best, val, stats = None, None, None
    for k in range(args.runs):
        p, dt = run_solve(argv, text, args.limit)
        if p is None:
            return "limit(time)", None, None
        out = json.loads(p.stdout) if p.stdout.strip() else {}
        if out.get("status") != "optimal":
            return ("limit(" + out.get("limit", "?") + ")") if out.get("status") in ("unknown", "feasible") else (out.get("status") or p.stderr.strip()[:60]), None, out.get("stats")
        val, stats = out["objective"], out["stats"]
        best = dt if best is None else min(best, dt)
        if best > 5.0:
            break
    return max(best - floor, 1e-4), val, stats


def matrices(model):
    n = len(model["variables"])
    c = np.zeros(n)
    for j, a in model["objective"]["terms"]:
        c[j] += a
    ri, ci, vals, lo, hi = [], [], [], [], []
    for r, row in enumerate(model["constraints"]):
        for j, a in row["terms"]:
            ri.append(r)
            ci.append(j)
            vals.append(a)
        s, b = row["sense"], row["rhs"]
        lo.append(b if s in (">=", "==") else -np.inf)
        hi.append(b if s in ("<=", "==") else np.inf)
    A = coo_matrix((vals, (ri, ci)), shape=(len(model["constraints"]), n)).tocsr()
    return c, A, np.array(lo), np.array(hi)


def timed_runs(f):
    best = None
    for _ in range(args.runs):
        r, dt = f()
        if r is None:
            return "limit", None
        best = dt if best is None else min(best, dt)
        val = r
        if best > 5.0:
            break
    return best, val


def highs_mip(model, mats):
    c, A, lo, hi = mats
    integ = np.array([1 if v["kind"] in ("bool", "int") else 0 for v in model["variables"]])
    bounds = Bounds([v["lo"] for v in model["variables"]], [v["hi"] for v in model["variables"]])

    def f():
        t = time.perf_counter()
        r = milp(c, constraints=LinearConstraint(A, lo, hi), integrality=integ, bounds=bounds, options={"time_limit": args.limit, "mip_rel_gap": 1e-9})
        dt = time.perf_counter() - t
        return (r.fun + model["objective"]["constant"] if r.status == 0 else None), dt
    return timed_runs(f)


def highs_lp(model, mats):
    c, A, lo, hi = mats
    integ = np.zeros(len(model["variables"]))
    bounds = Bounds([v["lo"] for v in model["variables"]], [v["hi"] for v in model["variables"]])

    def f():
        t = time.perf_counter()
        r = milp(c, constraints=LinearConstraint(A, lo, hi), integrality=integ, bounds=bounds, options={"time_limit": args.limit})
        dt = time.perf_counter() - t
        return (r.fun + model["objective"]["constant"] if r.status == 0 else None), dt
    return timed_runs(f)


def ortools_solve(model, name, integer):
    def f():
        s = pywraplp.Solver.CreateSolver(name)
        inf = s.infinity()
        xs = [(s.IntVar if (integer and v["kind"] in ("bool", "int")) else s.NumVar)(v["lo"], v["hi"], "") for v in model["variables"]]
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
        s.SetTimeLimit(int(args.limit * 1000))
        prm = pywraplp.MPSolverParameters()
        prm.SetDoubleParam(pywraplp.MPSolverParameters.RELATIVE_MIP_GAP, 1e-9)   # the default 1e-4 stops a solver at an answer our exact search would not call optimal
        t = time.perf_counter()
        st = s.Solve(prm)
        dt = time.perf_counter() - t
        return (o.Value() if st == pywraplp.Solver.OPTIMAL else None), dt
    return timed_runs(f)


def fmt(x):
    return x if isinstance(x, str) else ("<0.001" if x < 0.001 else f"{x:.3f}")


def agree(a, b):
    return isinstance(a, float) and isinstance(b, float) and abs(a - b) <= 1e-6 * (1 + abs(b))


results, bad = [], 0
print(f"machine: {platform.platform()}, {platform.machine()}; python {platform.python_version()}; ortools {ortools.__version__}; limit {args.limit}s; runs: minimum of {args.runs} under 5 s; ours: {SOLVE}", flush=True)
for setting in ["tight", "ample"]:
    for V, T in (SIZES[setting] if setting in args.settings.split(',') else []):
        if V > args.max_v:
            continue
        text = generate(V, T, setting, 7)
        p, _ = run_solve(["expand"], text, 120)
        if p is None or p.returncode != 0:
            print(f"{setting} {V}x{T}: expand failed: {p.stderr[:200] if p else 'timeout'}", flush=True)
            bad += 1
            continue
        model = json.loads(p.stdout)
        mats = matrices(model)
        cols, rows_ = len(model["variables"]), len(model["constraints"])
        row = dict(setting=setting, V=V, T=T, columns=cols, rows=rows_)
        row["highs_lp"], hlv = highs_lp(model, mats)
        row["glop"], glv = ortools_solve(model, "GLOP", False)
        row["clp"], clv = ortools_solve(model, "CLP", False)
        row["ours_lp"], olv, ost = ours(text, True)
        row["highs_mip"], hmv = highs_mip(model, mats)
        row["scip"], scv = ortools_solve(model, "SCIP", True)
        row["cbc"], cbv = ortools_solve(model, "CBC", True)
        row["ours_mip"], omv, mst = ours(text, False)
        row["ours_nodes"] = (mst or {}).get("nodes")
        row["ours_cuts"] = (mst or {}).get("cuts")
        row["ours_method"] = (mst or ost or {}).get("method", "sparse")
        status = "ok"
        for name, mine, ref in [("lp", olv, hlv), ("glop", glv, hlv), ("clp", clv, hlv), ("mip", omv, hmv), ("scip", scv, hmv), ("cbc", cbv, hmv)]:
            if isinstance(mine, float) and isinstance(ref, float) and not agree(mine, ref):
                status = f"DISAGREES ({name}: {mine} against {ref})"
                bad += 1
        row["answer"] = status
        results.append(row)
        print(json.dumps(row), flush=True)

head = ["setting", "V x T", "cols", "rows", "LP: HiGHS", "GLOP", "CLP", "ours", "MIP: HiGHS", "SCIP", "CBC", "ours", "ours nodes", "answer"]
lines = [head] + [[r["setting"], f"{r['V']}x{r['T']}", str(r["columns"]), str(r["rows"]), fmt(r["highs_lp"]), fmt(r["glop"]), fmt(r["clp"]), fmt(r["ours_lp"]), fmt(r["highs_mip"]), fmt(r["scip"]), fmt(r["cbc"]), fmt(r["ours_mip"]), str(r["ours_nodes"] if r["ours_nodes"] is not None else "-"), r["answer"]] for r in results]
widths = [max(len(l[i]) for l in lines) for i in range(len(head))]
table = "\n".join("  ".join(c.ljust(w) for c, w in zip(l, widths)) for l in lines)
header = f"machine: {platform.platform()}, {platform.machine()}; python {platform.python_version()}; ortools {ortools.__version__}; limit {args.limit}s; ours: minimum of {args.runs} runs under 5 s minus `solve check`; others: solver call only; seconds\n"
print(table)
os.makedirs(os.path.dirname(args.out), exist_ok=True)
open(args.out + ".txt", "w").write(header + table + "\n")
json.dump(dict(machine=f"{platform.platform()}, {platform.machine()}", ortools=ortools.__version__, limit=args.limit, runs=args.runs, rows=results), open(args.out + ".json", "w"), indent=1)
sys.exit(1 if bad else 0)
