#!/usr/bin/env python3
"""Gate 4 (docs/design.md section 14): `solve run --relax` and HiGHS (scipy.optimize.linprog) agree on status and objective on fixed-seed random LPs,
and the printed solution satisfies the expanded model when re-evaluated here."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve, highs, violation, objective_of

SOLVE = os.environ.get("SOLVE", "build/solve")
cases = []
for seed in range(120):
    cases.append((f"random {seed}", lpgen.random_lp(seed, 2 + seed % 9, 2 + (seed * 7) % 11, 0.6, infeasible=(seed % 6 == 5))))
for seed in range(30):
    cases.append((f"medium {seed}", lpgen.random_lp(1000 + seed, 15 + seed % 20, 20 + (seed * 3) % 30, 0.3, infeasible=(seed % 10 == 9))))
for seed in range(6):
    cases.append((f"transport {seed}", lpgen.transportation(seed, 3 + seed, 4 + seed)))
for seed in range(6):
    cases.append((f"assignment {seed}", lpgen.assignment(seed, 3 + seed)))
for seed in range(6):
    cases.append((f"mkp {seed}", lpgen.mkp(seed, 10 + 3 * seed, 2 + seed % 3)))

bad = 0
stats = {"optimal": 0, "infeasible": 0}
for name, text in cases:
    p, _ = run_solve(SOLVE, ["expand"], text)
    if p.returncode != 0:
        print(f"FAIL {name}: expand refused: {p.stderr.strip()}")
        bad += 1
        continue
    model = json.loads(p.stdout)
    hstatus, hobj, _, _ = highs(model)
    q, _ = run_solve(SOLVE, ["run", "--relax"], text)
    if q.returncode not in (0, 1):
        print(f"FAIL {name}: run status {q.returncode}: {q.stderr.strip()[:200]}")
        bad += 1
        continue
    got = json.loads(q.stdout)
    if hstatus == 2:
        stats["infeasible"] += 1
        if got["status"] != "infeasible":
            print(f"FAIL {name}: HiGHS says infeasible, we say {got['status']}")
            bad += 1
        continue
    if hstatus != 0:
        print(f"SKIP {name}: HiGHS status {hstatus}")
        continue
    stats["optimal"] += 1
    if got["status"] != "optimal":
        print(f"FAIL {name}: HiGHS optimal {hobj}, we say {got['status']}")
        bad += 1
        continue
    if abs(got["objective"] - hobj) > 1e-6 * (1 + abs(hobj)):
        print(f"FAIL {name}: objective {got['objective']} against HiGHS {hobj}")
        bad += 1
        continue
    v = violation(model, got["x"])
    if v > 1e-6:
        print(f"FAIL {name}: printed solution violates the model by {v}")
        bad += 1
        continue
    if abs(objective_of(model, got["x"]) - got["objective"]) > 1e-6 * (1 + abs(hobj)):
        print(f"FAIL {name}: printed objective is not the objective of the printed solution")
        bad += 1
        continue
    if not got["verified"]:
        print(f"FAIL {name}: verified is false on a correct answer")
        bad += 1

print(f"oracle gate: {'FAILED' if bad else 'passed'} ({len(cases)} cases: {stats['optimal']} optimal, {stats['infeasible']} infeasible, {bad} failures)")
sys.exit(1 if bad else 0)
