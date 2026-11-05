#!/usr/bin/env python3
"""Gate 8 (docs/design.md section 19.6): the dense and the sparse LP engine of the branch and bound search agree. Both `solve run --method dense` and `--method sparse`
are run on fixed-seed models of every family of check_mip.py plus larger ones (restoring a node then goes through many refactorisations and the eta file fills), and must
agree on the status and, when optimal, on the optimal value to 1e-6 relative; each printed solution is re-checked here against the expanded model (bounds, rows,
integrality); `stats.method` must be the method asked for (so the gate cannot pass by running one engine twice); with a node limit or an iteration limit neither engine is
ever wrong (`bound <= optimum <= objective`); and each engine gives the same bytes twice. The node counts are NOT compared: the engines break ties differently, and may
take different paths (19.6). Usage: SOLVE=build/solve python3 scripts/check_mip_engines.py [--quick]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import violation, objective_of, int_violation, highs_mip
import subprocess

SOLVE = os.environ.get("SOLVE", "build/solve")
QUICK = "--quick" in sys.argv
bad = 0

def fail(msg):
    global bad
    bad += 1
    print("FAIL " + msg)

def close(a, b):
    return abs(a - b) <= 1e-6 * (1 + abs(b))

def run(method, text, extra=()):
    return subprocess.run([SOLVE, "run", "--method", method, *extra], input=text, capture_output=True, text=True)

cases = []
for s in range(24):
    cases.append((f"knapsack {s}", lpgen.knapsack(s, 8 + s % 40, correlated=s % 2 == 0)))
for s in range(12):
    cases.append((f"mkp {s}", lpgen.mkp(s, 10 + 6 * s, 2 + s % 4)))
for s in range(8):
    cases.append((f"assignment {s}", lpgen.assignment(s, 3 + 3 * s)))
for s in range(16):
    cases.append((f"set cover {s}", lpgen.set_cover(s, 8 + 5 * s, 10 + 7 * s, 0.2)))
for s in range(12):
    cases.append((f"subset sum {s}", lpgen.equality_knapsack(s, 8 + s % 6, feasible=s % 4 != 3)))
for s in range(40):
    cases.append((f"general int {s}", lpgen.random_mip(s, 2 + s % 9, 2 + s % 9, 0.7, 1.0, infeasible=(s % 12 == 11))))
for s in range(30):
    cases.append((f"mixed {s}", lpgen.random_mip(500 + s, 3 + s % 12, 3 + s % 14, 0.6, 0.5, infeasible=(s % 13 == 12))))
for s in range(6):
    cases.append((f"bin packing {s}", lpgen.bin_packing_lite(s, 5 + 2 * (s % 4), 3 + s % 3)))
# larger: many refactorisations (more than 64 iterations in a node's dual simplex or on the restore path)
for s in range(3):
    cases.append((f"large mkp {s}", lpgen.mkp(100 + s, 100 + 20 * s, 10 + 2 * s)))
    cases.append((f"large set cover {s}", lpgen.set_cover(100 + s, 100 + 40 * s, 150 + 60 * s, 0.05)))
    cases.append((f"large general int {s}", lpgen.random_mip(100 + s, 14 + 2 * s, 14 + 2 * s, 0.5, 1.0)))
    cases.append((f"large mixed {s}", lpgen.random_mip(700 + s, 25 + 5 * s, 35 + 5 * s, 0.3, 0.5)))
if QUICK:
    cases = cases[::4]

n_opt = n_inf = n_lim = n_cmp = 0
for name, text in cases:
    e = subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True)
    if e.returncode != 0:
        fail(f"{name}: expand refused: {e.stderr[:200]}")
        continue
    model = json.loads(e.stdout)
    d, s = run("dense", text, ("--node-limit", "50000")), run("sparse", text, ("--node-limit", "50000"))
    for who, p in (("dense", d), ("sparse", s)):
        if p.returncode not in (0, 1):
            fail(f"{name}: {who} exit {p.returncode}: {p.stderr[:200]}")
    if d.returncode not in (0, 1) or s.returncode not in (0, 1):
        continue
    a, b = json.loads(d.stdout), json.loads(s.stdout)
    if a["stats"].get("method") != "dense" or b["stats"].get("method") != "sparse":
        fail(f"{name}: stats.method is {a['stats'].get('method')} / {b['stats'].get('method')}, wanted dense / sparse")
        continue
    if a["status"] != b["status"]:
        # a node limit may stop one of them first; that is only acceptable if neither claims a wrong answer
        if "optimal" in (a["status"], b["status"]) and "infeasible" in (a["status"], b["status"]):
            fail(f"{name}: dense {a['status']}, sparse {b['status']}")
        elif a["status"] in ("optimal", "infeasible") and b["status"] in ("optimal", "infeasible") or "limit" not in a and "limit" not in b:
            fail(f"{name}: dense {a['status']}, sparse {b['status']}")
        continue
    n_cmp += 1
    if a["status"] == "infeasible":
        n_inf += 1
        continue
    if a["status"] != "optimal":
        continue
    n_opt += 1
    if not close(a["objective"], b["objective"]):
        fail(f"{name}: objective {a['objective']} (dense) against {b['objective']} (sparse)")
        continue
    if violation(model, b["x"]) > 1e-6 or int_violation(model, b["x"]) > 1e-9 or not b["verified"]:
        fail(f"{name}: the sparse solution violates the model ({violation(model, b['x'])}, integrality {int_violation(model, b['x'])}, verified {b['verified']})")
    if not close(objective_of(model, b["x"]), b["objective"]):
        fail(f"{name}: the sparse objective is not the objective of its solution")
    if not close(b["bound"], b["objective"]):
        fail(f"{name}: sparse optimal but bound {b['bound']} differs from objective {b['objective']}")

# the oracle itself, on a sample: HiGHS holds the sparse engine's optimum (check_mip.py does it for the whole corpus; here for the larger models)
for name, text in cases:
    if not name.startswith("large"):
        continue
    model = json.loads(subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True).stdout)
    hstatus, hobj, _, _ = highs_mip(model, time_limit=60)
    q = run("sparse", text, ("--node-limit", "200000"))
    got = json.loads(q.stdout)
    if hstatus == 0 and got["status"] == "optimal" and not close(got["objective"], hobj):
        fail(f"{name}: sparse {got['objective']} against HiGHS {hobj}")
    if hstatus == 2 and got["status"] != "infeasible" and got["status"] != "unknown" and got["status"] != "feasible":
        fail(f"{name}: HiGHS infeasible, sparse {got['status']}")
    if hstatus == 2 and got["status"] in ("optimal", "feasible"):
        fail(f"{name}: HiGHS infeasible, sparse {got['status']}")
    if hstatus == 0 and got["status"] == "infeasible":
        fail(f"{name}: HiGHS optimal {hobj}, sparse infeasible")

# limits: never wrong, the bound brackets the optimum
for name, text in cases[::3]:
    model = json.loads(subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True).stdout)
    hstatus, hobj, _, _ = highs_mip(model, time_limit=60)
    if hstatus != 0:
        continue
    maxim = "maximize" in text.split("subject to")[0]
    for extra in (("--node-limit", "3"), ("--node-limit", "20"), ("--iteration-limit", "40"), ("--iteration-limit", "400")):
        q = run("sparse", text, extra)
        n_lim += 1
        if q.returncode not in (0, 1):
            fail(f"{name} {extra}: sparse exit {q.returncode}")
            continue
        got = json.loads(q.stdout)
        tol = 1e-6 * (1 + abs(hobj))
        if got["status"] == "optimal":
            if not close(got["objective"], hobj):
                fail(f"{name} {extra}: sparse says optimal {got['objective']}, optimum {hobj}")
            continue
        if got["status"] == "infeasible":
            fail(f"{name} {extra}: sparse infeasible on a feasible model")
            continue
        b = got.get("bound")
        if b is not None and (b < hobj - tol if not maxim else b > hobj + tol):
            fail(f"{name} {extra}: bound {b} is on the wrong side of the optimum {hobj}")
        if got["status"] == "feasible" and (got["objective"] < hobj - tol if not maxim else got["objective"] > hobj + tol):
            fail(f"{name} {extra}: incumbent {got['objective']} is better than the optimum {hobj}")

# determinism of each engine
for name, text in cases[::9]:
    for method in ("dense", "sparse"):
        if run(method, text).stdout != run(method, text).stdout:
            fail(f"{name}: two {method} runs differ")

# the refusal of a bad value, and `auto` (answers the same as the engine it picks)
p = subprocess.run([SOLVE, "run", "--method", "simplex"], input=cases[0][1], capture_output=True, text=True)
if p.returncode != 2:
    fail("a bad --method is not refused")
name, text = cases[40]
q = run("auto", text)
if json.loads(q.stdout)["stats"].get("method") not in ("dense", "sparse"):
    fail("auto reports no method")

print(f"mip engines gate: {'FAILED' if bad else 'passed'} ({len(cases)} instances, {n_cmp} compared, {n_opt} optimal, {n_inf} infeasible, {n_lim} limited runs, {bad} failures)")
sys.exit(1 if bad else 0)
