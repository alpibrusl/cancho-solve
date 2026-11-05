#!/usr/bin/env python3
"""Gate 5 (docs/design.md section 17): the pricing and the long step are judged by how many iterations they take, which the oracle does not see (a worse rule still
finds the optimum). Fixed instances (seed 7, deterministic), the iteration count of `solve run --relax` must stay under a bound set at about 1.25 times what the
steepest-edge rule with the long step takes. Without the long step the knapsack takes 1,930 iterations (not 130) and without the pricing the dense LP takes 1,234
(not 323): both fail here. Usage: SOLVE=build/solve python3 scripts/check_iterations.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve

SOLVE = os.environ.get("SOLVE", "build/solve")
# (name, model, bound for the dense solver, bound for the sparse one). The sparse solver updates its weights by formula instead of recomputing them (design.md 18.3.2), so its
# counts differ a little: measured 353, 164, 130, 218 against the dense 323, 164, 130, 214; its bounds are 1.25 times its own counts.
METHOD = os.environ.get("SOLVE_METHOD", "dense")
CASES = [
    ("random dense LP 200x400", lpgen.random_lp(7, 200, 400, 0.5), 400, 441),
    ("random dense LP 100x200", lpgen.random_lp(7, 100, 200, 0.5), 205, 205),
    ("multi-knapsack 1000 items, 50 rows", lpgen.mkp(7, 1000, 50), 165, 165),
    ("assignment 100x100", lpgen.assignment(7, 100), 270, 273),
]
# exact counts: the rule is deterministic, and a change of the weight of one row moves these by a few iterations (found by the mutant "the pivot row's weight is not
# taken from the row": 65 and 61 instead of 63 and 59). A deliberate change of the pivoting rule changes these numbers on purpose and they are then re-measured.
EXACT = [
    ("assignment 30x30, seed 1", lpgen.assignment(1, 30), 63),
    ("transportation 20x40, seed 9", lpgen.transportation(9, 20, 40), 59),
]
bad = 0
for name, text, want in EXACT:
    p, _ = run_solve(SOLVE, ["run", "--relax"], text)
    it = json.loads(p.stdout)["stats"]["iterations"]
    if p.returncode != 0 or it != want:
        bad += 1
        print(f"FAIL {name}: {it} iterations, exactly {want} expected, status {p.returncode}")
    else:
        print(f"ok   {name}: {it} iterations (exact)")
for name, text, bound_dense, bound_sparse in CASES:
    bound = bound_sparse if METHOD == "sparse" else bound_dense
    p, _ = run_solve(SOLVE, ["run", "--relax"], text)
    r = json.loads(p.stdout)
    it = r["stats"]["iterations"]
    if p.returncode != 0 or it > bound:
        bad += 1
        print(f"FAIL {name}: {it} iterations, bound {bound}, status {p.returncode}")
    else:
        print(f"ok   {name}: {it} iterations (bound {bound})")
print("iteration gate:", "FAILED" if bad else "passed", f"({len(CASES) + len(EXACT)} cases, {bad} failures)")
sys.exit(1 if bad else 0)
