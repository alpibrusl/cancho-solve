#!/usr/bin/env python3
"""Benchmark of `solve run` on integer models against HiGHS (scipy.optimize.milp), OR-Tools SCIP (pywraplp) and CP-SAT (docs/design.md section 19.3, results in 19.5).
Usage: SOLVE=build/solve python bench_mip.py [--runs N] [--limit SECONDS] [--families a,b] [--ablate]
  default: each instance by every solver. --ablate: only ours, under the option sets of section 19.5 (nodes and iterations)."""
import json, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import highs_mip

SOLVE = os.environ.get("SOLVE", "build/solve")
args = sys.argv[1:]
RUNS = int(args[args.index("--runs") + 1]) if "--runs" in args else 3
LIMIT = float(args[args.index("--limit") + 1]) if "--limit" in args else 60.0
FAM = args[args.index("--families") + 1].split(",") if "--families" in args else None
ABLATE = "--ablate" in args

INSTANCES = [
    ("knapsack", "30 items", lambda: lpgen.knapsack(7, 30)),
    ("knapsack", "60 items", lambda: lpgen.knapsack(7, 60)),
    ("knapsack", "100 items", lambda: lpgen.knapsack(7, 100)),
    ("knapsack", "200 items", lambda: lpgen.knapsack(7, 200)),
    ("knapsack", "500 items", lambda: lpgen.knapsack(7, 500)),
    ("knapsack", "1000 items", lambda: lpgen.knapsack(7, 1000)),
    ("mkp", "30 x 5", lambda: lpgen.mkp(7, 30, 5)),
    ("mkp", "50 x 5", lambda: lpgen.mkp(7, 50, 5)),
    ("mkp", "50 x 10", lambda: lpgen.mkp(7, 50, 10)),
    ("mkp", "100 x 10", lambda: lpgen.mkp(7, 100, 10)),
    ("mkp", "100 x 20", lambda: lpgen.mkp(7, 100, 20)),
    ("mkp", "200 x 10", lambda: lpgen.mkp(7, 200, 10)),
    ("assignment", "20 x 20", lambda: lpgen.assignment(7, 20)),
    ("assignment", "50 x 50", lambda: lpgen.assignment(7, 50)),
    ("assignment", "100 x 100", lambda: lpgen.assignment(7, 100)),
    ("set cover", "30 rows, 50 sets", lambda: lpgen.set_cover(7, 30, 50, 0.1)),
    ("set cover", "60 rows, 100 sets", lambda: lpgen.set_cover(7, 60, 100, 0.08)),
    ("set cover", "120 rows, 200 sets", lambda: lpgen.set_cover(7, 120, 200, 0.05)),
    ("set cover", "200 rows, 400 sets", lambda: lpgen.set_cover(7, 200, 400, 0.03)),
    ("set cover", "300 rows, 300 sets, dense", lambda: lpgen.set_cover(7, 300, 300, 0.05)),
    ("set cover", "400 rows, 600 sets", lambda: lpgen.set_cover(7, 400, 600, 0.02)),
    ("general int", "10 x 10", lambda: lpgen.random_mip(7, 10, 10, 0.5, 1.0)),
    ("general int", "20 x 20", lambda: lpgen.random_mip(7, 20, 20, 0.4, 1.0)),
    ("general int", "30 x 30", lambda: lpgen.random_mip(7, 30, 30, 0.3, 1.0)),
    ("general int", "40 x 40", lambda: lpgen.random_mip(7, 40, 40, 0.3, 1.0)),
    ("general int", "50 x 50", lambda: lpgen.random_mip(7, 50, 50, 0.2, 1.0)),
    ("mixed", "30 x 40", lambda: lpgen.random_mip(7, 30, 40, 0.3, 0.5)),
    ("bin packing", "8 items, 4 bins", lambda: lpgen.bin_packing_lite(7, 8, 4)),
    ("bin packing", "12 items, 6 bins", lambda: lpgen.bin_packing_lite(7, 12, 6)),
    ("bin packing", "15 items, 8 bins", lambda: lpgen.bin_packing_lite(7, 15, 8)),
    ("bin packing", "20 items, 10 bins", lambda: lpgen.bin_packing_lite(7, 20, 10)),
]

def ours(text, extra=(), timeout=LIMIT):
    best = None
    out = None
    for _ in range(RUNS):
        t = time.perf_counter()
        try:
            p = subprocess.run([SOLVE, "run", *extra], input=text, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, timeout
        dt = time.perf_counter() - t
        out = json.loads(p.stdout) if p.stdout else {"status": "refused"}
        best = dt if best is None else min(best, dt)
        if dt > 5:
            break
    return out, best

def scip(model):
    from ortools.linear_solver import pywraplp
    sc = pywraplp.Solver.CreateSolver("SCIP")
    xs = [sc.IntVar(v["lo"], v["hi"], v["name"]) if v["kind"] != "real" else sc.NumVar(v["lo"], v["hi"], v["name"]) for v in model["variables"]]
    for r in model["constraints"]:
        e = sum(a * xs[j] for j, a in r["terms"])
        sc.Add(e <= r["rhs"] if r["sense"] == "<=" else e >= r["rhs"] if r["sense"] == ">=" else e == r["rhs"])
    ob = model["objective"]
    e = sum(a * xs[j] for j, a in ob["terms"]) + ob["constant"]
    (sc.Minimize if ob["sense"] == "minimize" else sc.Maximize)(e)
    sc.SetTimeLimit(int(LIMIT * 1000))
    sc.SetNumThreads(1)
    t = time.perf_counter()
    st = sc.Solve()
    dt = time.perf_counter() - t
    return ("optimal" if st == pywraplp.Solver.OPTIMAL else "limit/other"), (sc.Objective().Value() if st in (0, 1) else None), dt, sc.nodes()

def cpsat(model):
    from ortools.sat.python import cp_model
    if any(v["kind"] == "real" for v in model["variables"]):
        return None
    cm = cp_model.CpModel()
    xs = [cm.NewIntVar(int(v["lo"]), int(v["hi"]), v["name"]) for v in model["variables"]]
    for r in model["constraints"]:
        e = sum(int(a) * xs[j] for j, a in r["terms"])
        cm.Add(e <= int(r["rhs"]) if r["sense"] == "<=" else e >= int(r["rhs"]) if r["sense"] == ">=" else e == int(r["rhs"]))
    ob = model["objective"]
    e = sum(int(a) * xs[j] for j, a in ob["terms"]) + int(ob["constant"])
    (cm.Minimize if ob["sense"] == "minimize" else cm.Maximize)(e)
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = LIMIT
    sv.parameters.num_workers = 1
    t = time.perf_counter()
    st = sv.Solve(cm)
    dt = time.perf_counter() - t
    return ("optimal" if st == cp_model.OPTIMAL else "limit/other"), (sv.ObjectiveValue() if st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None), dt, sv.NumBranches()

SETS = [("depth+fractional", ["--node-select", "depth", "--branching", "fractional"]), ("best+fractional", ["--branching", "fractional"]), ("depth+pseudo", ["--node-select", "depth"]), ("best+pseudo (default)", []),
        ("no whole-obj cut", ["--experiment", "1"]), ("no rounding", ["--experiment", "2"]), ("far child first", ["--experiment", "4"])]

def fmt(x, p=3):
    return "-" if x is None else (f"{x:.{p}f}" if isinstance(x, float) else str(x))

if ABLATE:
    print("| family | size | " + " | ".join(n for n, _ in SETS) + " |")
    print("|---|---|" + "---|" * len(SETS))
    for fam, size, mk in INSTANCES:
        if FAM and fam not in FAM:
            continue
        text = mk()
        cells = []
        for name, extra in SETS:
            r, dt = ours(text, extra)
            if r is None:
                cells.append(f"timeout>{LIMIT:.0f}s")
            else:
                st = r["stats"]
                cells.append(f"{r['status'][:3]} {st.get('nodes', '-')}n {st['iterations']}it {dt:.2f}s")
        print(f"| {fam} | {size} | " + " | ".join(cells) + " |", flush=True)
    sys.exit(0)

print("| family | size | rows x cols | ours | nodes | iters | HiGHS | nodes | SCIP | nodes | CP-SAT | branches | objective agrees |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for fam, size, mk in INSTANCES:
    if FAM and fam not in FAM:
        continue
    text = mk()
    model = json.loads(subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True).stdout)
    r, dt = ours(text)
    h = highs_mip(model, time_limit=LIMIT)
    s = scip(model)
    c = cpsat(model)
    objs = []
    if r is not None and r["status"] == "optimal":
        objs.append(("ours", r["objective"]))
    if h[0] == 0:
        objs.append(("highs", h[1]))
    if s[1] is not None and s[0] == "optimal":
        objs.append(("scip", s[1]))
    if c is not None and c[1] is not None and c[0] == "optimal":
        objs.append(("cpsat", c[1]))
    agree = all(abs(v - objs[0][1]) <= 1e-6 * (1 + abs(objs[0][1])) for _, v in objs) if objs else None
    if r is None:
        o = f">{LIMIT:.0f}s (timeout)"
        nodes = it = "-"
    else:
        o = f"{dt:.3f}s ({r['status']})" if r["status"] != "optimal" else f"{dt:.3f}s"
        nodes = r["stats"].get("nodes", "-")
        it = r["stats"]["iterations"]
    hs = f"{h[2]:.3f}s" + ("" if h[0] == 0 else f" (status {h[0]})")
    ss = f"{s[2]:.3f}s" + ("" if s[0] == "optimal" else " (limit)")
    cs = "-" if c is None else f"{c[2]:.3f}s" + ("" if c[0] == "optimal" else " (limit)")
    print(f"| {fam} | {size} | {len(model['constraints'])} x {len(model['variables'])} | {o} | {nodes} | {it} | {hs} | {h[3]} | {ss} | {s[3]} | {cs} | {'-' if c is None else c[3]} | {agree} |", flush=True)
