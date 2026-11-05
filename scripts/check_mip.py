#!/usr/bin/env python3
"""Gate 6 (docs/design.md section 19.2): `solve run` on models with integer variables.

1. tests/mip/*.sol: each file's `//~ EXPECT status [objective]` (derived by hand, in the file's comments), optional `//~ ARGS ...`, `//~ NODES n`, `//~ EXIT n`.
2. The oracle: fixed-seed generated instances (0/1 knapsack, multi-dimensional knapsack, assignment, set cover, subset sum, general-integer, mixed, infeasible) are expanded
   with `solve expand`, solved by HiGHS (scipy.optimize.milp) and by `solve run`, which must agree on status and optimal value (1e-6 relative); the printed x is re-evaluated
   here (bounds, rows, integrality); tiny all-integer instances are also solved by exhaustive enumeration (a third opinion that shares no code with either solver).
3. Limits: with a node limit the answer is `optimal` or `feasible`/`unknown`, never wrong: `bound <= optimum <= objective` (minimisation; mirrored for maximisation).
4. Determinism: the same model and options give the same bytes (twice).
5. `--ortools`: CP-SAT and SCIP (pywraplp) as a second oracle on the integer-coefficient instances.
Usage: SOLVE=build/solve python3 scripts/check_mip.py [--ortools] [--quick]"""
import glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve, highs_mip, violation, objective_of, int_violation, brute_force

SOLVE = os.environ.get("SOLVE", "build/solve")
ORT = "--ortools" in sys.argv
QUICK = "--quick" in sys.argv
bad = 0

def fail(msg):
    global bad
    bad += 1
    print("FAIL " + msg)

def close(a, b):
    return abs(a - b) <= 1e-6 * (1 + abs(b))

# ---- 1. hand-derived models
n_hand = 0
for path in sorted(glob.glob("tests/mip/*.sol")):
    text = open(path).read()
    exp = re.search(r"//~ EXPECT (\w+)(?: (\S+))?", text)
    args = re.search(r"//~ ARGS (.*)", text)
    nodes = re.search(r"//~ NODES (\d+)", text)
    ext = re.search(r"//~ EXIT (\d+)", text)
    lim = re.search(r"//~ LIMIT (\S+)", text)
    p, _ = run_solve(SOLVE, ["run"] + (args.group(1).split() if args else []), text)
    n_hand += 1
    want_exit = int(ext.group(1)) if ext else 0
    if p.returncode != want_exit:
        fail(f"{path}: exit {p.returncode}, wanted {want_exit}: {p.stderr[:200]}")
        continue
    got = json.loads(p.stdout)
    if got["status"] != exp.group(1):
        fail(f"{path}: status {got['status']}, wanted {exp.group(1)}")
        continue
    if exp.group(2) is not None and not close(got["objective"], float(exp.group(2))):
        fail(f"{path}: objective {got['objective']}, wanted {exp.group(2)}")
    if nodes and got["stats"]["nodes"] != int(nodes.group(1)):
        fail(f"{path}: {got['stats']['nodes']} nodes, wanted {nodes.group(1)}")
    if lim and got.get("limit") != lim.group(1):
        fail(f"{path}: limit {got.get('limit')}, wanted {lim.group(1)}")
    if got["status"] in ("optimal", "feasible"):
        if not got.get("verified"):
            fail(f"{path}: verified is false")
    if got["status"] in ("feasible", "unknown") and "bound" not in got and "iteration-limit 0" not in (args.group(1) if args else ""):
        fail(f"{path}: a limited run prints no bound")

# ---- 2. generated instances
cases = []
for s in range(30):
    cases.append((f"knapsack {s}", lpgen.knapsack(s, 8 + s % 20, correlated=s % 2 == 0)))
for s in range(12):
    cases.append((f"mkp {s}", lpgen.mkp(s, 10 + 2 * s, 2 + s % 3)))
for s in range(10):
    cases.append((f"assignment {s}", lpgen.assignment(s, 3 + s)))
for s in range(20):
    cases.append((f"set cover {s}", lpgen.set_cover(s, 8 + s, 10 + s, 0.2)))
for s in range(16):
    cases.append((f"subset sum {s}", lpgen.equality_knapsack(s, 8 + s % 6, feasible=s % 4 != 3)))
for s in range(60):
    cases.append((f"general int {s}", lpgen.random_mip(s, 2 + s % 5, 2 + s % 5, 0.7, 1.0, infeasible=(s % 12 == 11))))
for s in range(40):
    cases.append((f"mixed {s}", lpgen.random_mip(500 + s, 3 + s % 6, 3 + s % 7, 0.6, 0.5, infeasible=(s % 13 == 12))))
for s in range(6):
    cases.append((f"bin packing {s}", lpgen.bin_packing_lite(s, 5 + s % 3, 3)))
if QUICK:
    cases = cases[::5]

stats = {"optimal": 0, "infeasible": 0, "skipped": 0, "brute": 0}
opt_of = {}
for name, text in cases:
    p, _ = run_solve(SOLVE, ["expand"], text)
    if p.returncode != 0:
        fail(f"{name}: expand refused: {p.stderr.strip()[:200]}")
        continue
    model = json.loads(p.stdout)
    hstatus, hobj, _, _ = highs_mip(model, time_limit=60)
    q, _ = run_solve(SOLVE, ["run"], text)
    if q.returncode not in (0, 1):
        fail(f"{name}: run exit {q.returncode}: {q.stderr.strip()[:200]}")
        continue
    got = json.loads(q.stdout)
    if hstatus not in (0, 2):
        stats["skipped"] += 1
        print(f"SKIP {name}: HiGHS status {hstatus}")
        continue
    bf = brute_force(model)
    if bf != "big":
        stats["brute"] += 1
        if (bf is None) != (hstatus == 2) or (bf is not None and not close(bf, hobj)):
            fail(f"{name}: enumeration says {bf}, HiGHS says status {hstatus} objective {hobj}: the oracle itself is wrong")
            continue
    if hstatus == 2:
        stats["infeasible"] += 1
        if got["status"] != "infeasible" or q.returncode != 0:
            fail(f"{name}: HiGHS infeasible, we say {got['status']} (exit {q.returncode})")
        continue
    stats["optimal"] += 1
    opt_of[name] = hobj
    if got["status"] != "optimal" or q.returncode != 0:
        fail(f"{name}: HiGHS optimal {hobj}, we say {got['status']} (exit {q.returncode}, limit {got.get('limit')})")
        continue
    if not close(got["objective"], hobj):
        fail(f"{name}: objective {got['objective']} against HiGHS {hobj}")
        continue
    if violation(model, got["x"]) > 1e-6 or int_violation(model, got["x"]) > 1e-9:
        fail(f"{name}: the printed solution violates the model ({violation(model, got['x'])}, integrality {int_violation(model, got['x'])})")
        continue
    if not close(objective_of(model, got["x"]), got["objective"]):
        fail(f"{name}: printed objective is not the objective of the printed solution")
    if not got["verified"]:
        fail(f"{name}: verified is false on a correct answer")
    if "nodes" in got["stats"] and not close(got["bound"], got["objective"]):
        fail(f"{name}: optimal but bound {got['bound']} differs from objective {got['objective']}")

# ---- 3. limits: never wrong, and the bound brackets the optimum
n_lim = 0
for name, text in cases:
    if name not in opt_of or not (name.startswith(("knapsack", "mkp", "set cover", "general int", "mixed"))):
        continue
    for lim in (1, 3, 8):
        q, _ = run_solve(SOLVE, ["run", "--node-limit", str(lim)], text)
        got = json.loads(q.stdout)
        n_lim += 1
        opt = opt_of[name]
        maxim = "maximize" in text.split("subject to")[0]
        if got["status"] == "optimal":
            if not close(got["objective"], opt):
                fail(f"{name} node-limit {lim}: optimal {got['objective']} but the optimum is {opt}")
            continue
        if got["status"] not in ("feasible", "unknown") or q.returncode != 1 or got.get("limit") != "nodes":
            fail(f"{name} node-limit {lim}: status {got['status']} exit {q.returncode} limit {got.get('limit')}")
            continue
        b = got["bound"]
        tol = 1e-6 * (1 + abs(opt))
        if maxim:
            if not (b >= opt - tol):
                fail(f"{name} node-limit {lim}: bound {b} is below the optimum {opt} (maximise)")
            if got["status"] == "feasible" and not (got["objective"] <= opt + tol and b >= got["objective"] - tol):
                fail(f"{name} node-limit {lim}: objective {got['objective']} / bound {b} do not bracket {opt}")
        else:
            if not (b <= opt + tol):
                fail(f"{name} node-limit {lim}: bound {b} is above the optimum {opt} (minimise)")
            if got["status"] == "feasible" and not (got["objective"] >= opt - tol and b <= got["objective"] + tol):
                fail(f"{name} node-limit {lim}: objective {got['objective']} / bound {b} do not bracket {opt}")
        if got["status"] == "feasible":
            if "gap" not in got or got["gap"] < -1e-12:
                fail(f"{name} node-limit {lim}: no gap")
            model = json.loads(run_solve(SOLVE, ["expand"], text)[0].stdout)
            if violation(model, got["x"]) > 1e-6 or int_violation(model, got["x"]) > 1e-9:
                fail(f"{name} node-limit {lim}: the incumbent violates the model")

# ---- 4. determinism
n_det = 0
for name, text in cases[::7]:
    a, _ = run_solve(SOLVE, ["run"], text)
    b, _ = run_solve(SOLVE, ["run"], text)
    c, _ = run_solve(SOLVE, ["run", "--node-limit", "5"], text)
    d, _ = run_solve(SOLVE, ["run", "--node-limit", "5"], text)
    n_det += 1
    if a.stdout != b.stdout or c.stdout != d.stdout:
        fail(f"{name}: two runs differ")


# ---- 4b. every option reaches the same optimum (node selection, branching, the ablation bits)
n_opt = 0
OPTION_SETS = [["--node-select", "depth"], ["--branching", "fractional"], ["--node-select", "depth", "--branching", "fractional"], ["--experiment", "1"], ["--experiment", "2"], ["--experiment", "4"], ["--experiment", "7"]]
for name, text in cases[::2]:
    if name not in opt_of:
        continue
    for opt in OPTION_SETS:
        q, _ = run_solve(SOLVE, ["run"] + opt, text)
        n_opt += 1
        got = json.loads(q.stdout) if q.returncode in (0, 1) else {"status": "refused"}
        if got["status"] != "optimal" or not close(got["objective"], opt_of[name]):
            fail(f"{name} {' '.join(opt)}: {got['status']} {got.get('objective')} against HiGHS {opt_of[name]}")

# ---- 5. a second oracle: CP-SAT and SCIP, on instances with integer coefficients and integer variables only
n_ort = 0
if ORT:
    from ortools.sat.python import cp_model
    from ortools.linear_solver import pywraplp
    for name, text in cases:
        if name not in opt_of or name.startswith("mixed"):
            continue
        model = json.loads(run_solve(SOLVE, ["expand"], text)[0].stdout)
        if any(v["kind"] == "real" for v in model["variables"]):
            continue
        cm = cp_model.CpModel()
        xs = [cm.NewIntVar(int(v["lo"]), int(v["hi"]), v["name"]) for v in model["variables"]]
        for r in model["constraints"]:
            e = sum(int(a) * xs[j] for j, a in r["terms"])
            cm.Add(e <= int(r["rhs"]) if r["sense"] == "<=" else e >= int(r["rhs"]) if r["sense"] == ">=" else e == int(r["rhs"]))
        ob = model["objective"]
        e = sum(int(a) * xs[j] for j, a in ob["terms"]) + int(ob["constant"])
        (cm.Minimize if ob["sense"] == "minimize" else cm.Maximize)(e)
        sv = cp_model.CpSolver()
        sv.parameters.max_time_in_seconds = 60
        sv.parameters.num_workers = 1
        st = sv.Solve(cm)
        n_ort += 1
        if st != cp_model.OPTIMAL or not close(sv.ObjectiveValue(), opt_of[name]):
            fail(f"{name}: CP-SAT status {sv.StatusName(st)} objective {sv.ObjectiveValue() if st == cp_model.OPTIMAL else None}, HiGHS {opt_of[name]}")
            continue
        sc = pywraplp.Solver.CreateSolver("SCIP")
        sx = [sc.IntVar(v["lo"], v["hi"], v["name"]) for v in model["variables"]]
        for r in model["constraints"]:
            e = sum(a * sx[j] for j, a in r["terms"])
            sc.Add(e <= r["rhs"] if r["sense"] == "<=" else e >= r["rhs"] if r["sense"] == ">=" else e == r["rhs"])
        e = sum(a * sx[j] for j, a in ob["terms"]) + ob["constant"]
        (sc.Minimize if ob["sense"] == "minimize" else sc.Maximize)(e)
        sc.SetTimeLimit(60000)
        if sc.Solve() != pywraplp.Solver.OPTIMAL or not close(sc.Objective().Value(), opt_of[name]):
            fail(f"{name}: SCIP disagrees with HiGHS ({opt_of[name]})")

print(f"mip gate: {'FAILED' if bad else 'passed'} ({n_hand} hand-derived models; {len(cases)} generated: {stats['optimal']} optimal, {stats['infeasible']} infeasible, "
      f"{stats['skipped']} skipped, {stats['brute']} also by enumeration; {n_lim} limited runs; {n_det} determinism pairs; {n_opt} runs under other options; {n_ort} against CP-SAT and SCIP; {bad} failures)")
sys.exit(1 if bad else 0)
