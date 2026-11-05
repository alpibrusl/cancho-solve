#!/usr/bin/env python3
"""Gate 7 (docs/design.md section 18.3.2): the dense solver is the second oracle of the sparse one. Both `solve run --relax --method dense` and `--method sparse` are run on
fixed-seed models of every family, small and large (the large ones need many refactorisations: more than 256 iterations, the interval since design.md 21.2), and must agree on the status and, when optimal, on
the objective to 1e-6 relative; each printed solution must re-check (`verified`, and re-evaluated here against the expanded model); and with an iteration limit both must
stop with `unknown`. The two share no code below the model checker. Usage: SOLVE=build/solve python3 scripts/check_dense_vs_sparse.py"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import violation

import subprocess
SOLVE = os.environ.get("SOLVE", "build/solve")

def run(method, text, extra=()):
    p = subprocess.run([SOLVE, "run", "--relax", "--method", method, *extra], input=text, capture_output=True, text=True)
    return p

cases = []
for seed in range(60):
    cases.append((f"random {seed}", lpgen.random_lp(500 + seed, 3 + seed % 17, 4 + (seed * 5) % 23, 0.5, infeasible=(seed % 7 == 6))))
for seed in range(10):
    cases.append((f"random big {seed}", lpgen.random_lp(900 + seed, 60 + 10 * seed, 100 + 15 * seed, 0.3)))
for seed in range(8):
    cases.append((f"transport {seed}", lpgen.transportation(300 + seed, 8 + 4 * seed, 12 + 6 * seed)))
for seed in range(8):
    cases.append((f"assignment {seed}", lpgen.assignment(300 + seed, 8 + 5 * seed)))
for seed in range(6):
    cases.append((f"mkp {seed}", lpgen.mkp(300 + seed, 100 + 150 * seed, 5 + 6 * seed)))

def scaled_lp(seed, m, n, spread):
    """Rows and columns scaled by 10^(+-spread): coefficients over 6 orders of magnitude at spread 3 (the pivot-disagreement and refactorisation paths see real rounding)."""
    r = random.Random(seed)
    names = [f"v{j}" for j in range(n)]
    cs = [10.0 ** r.uniform(-spread, spread) for _ in range(n)]
    lines = [f"var {v} : real 0..{r.randint(1, 9)};" for v in names]
    lines.append("minimize " + " + ".join(f"{r.uniform(-1, 1) * cs[j]:.6g}*{names[j]}" for j in range(n)) + ";")
    lines.append("subject to")
    for i in range(m):
        rs = 10.0 ** r.uniform(-spread, spread)
        terms = [(j, r.uniform(-1, 1) * rs * cs[j]) for j in range(n) if r.random() < 0.4] or [(0, 1.0)]
        lines.append(f"  c{i}: " + " + ".join(f"{a:.6g}*{names[j]}" for j, a in terms) + f" <= {r.uniform(0, 3) * rs * sum(abs(a) for _, a in terms):.6g};")
    return "\n".join(lines) + "\n"

for spread in (1, 2, 3):
    for seed in range(4):
        cases.append((f"scaled {spread}.{seed}", scaled_lp(seed, 150, 300, spread)))
# models of more than 256 iterations, so that the refactorisation at the interval (256 since design.md 21.2; 64 before) is met inside the loop and not only at the start and the end
for seed in range(3):
    cases.append((f"random long {seed}", lpgen.random_lp(970 + seed, 250 + 20 * seed, 500 + 40 * seed, 0.3)))
    cases.append((f"flow long {seed}", lpgen.mincost_flow(980 + seed, 300 + 100 * seed, 1500 + 400 * seed)))
for spread in (2, 3):
    cases.append((f"scaled long {spread}", scaled_lp(40 + spread, 300, 600, spread)))
bad = 0
refac = 0
for name, text in cases:
    d, s = run("dense", text), run("sparse", text)
    if d.returncode not in (0, 1) or s.returncode not in (0, 1):
        print(f"FAIL {name}: dense status {d.returncode} {d.stderr[:100]}, sparse status {s.returncode} {s.stderr[:100]}")
        bad += 1
        continue
    a, b = json.loads(d.stdout), json.loads(s.stdout)
    if a["status"] != b["status"]:
        print(f"FAIL {name}: dense {a['status']}, sparse {b['status']}")
        bad += 1
        continue
    if a["status"] != "optimal":
        continue
    if abs(a["objective"] - b["objective"]) > 1e-6 * (1 + abs(a["objective"])):
        print(f"FAIL {name}: objective {a['objective']} (dense) against {b['objective']} (sparse)")
        bad += 1
        continue
    e = subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True)
    v = violation(json.loads(e.stdout), b["x"])
    if v > 1e-6 or not b["verified"]:
        print(f"FAIL {name}: the sparse solution violates the model by {v}, verified={b['verified']}")
        bad += 1
    if b["stats"]["iterations"] > 256:
        refac += 1

# the iteration limit: both stop with `unknown` and the sparse solver counts the iterations it made
text = lpgen.random_lp(7, 100, 200, 0.5)
for method in ("dense", "sparse"):
    p = run(method, text, ("--iteration-limit", "5"))
    r = json.loads(p.stdout)
    if p.returncode != 1 or r["status"] != "unknown" or r["stats"]["iterations"] != 5:
        print(f"FAIL iteration limit ({method}): status {p.returncode}, {p.stdout[:200]}")
        bad += 1
print(f"dense-vs-sparse gate: {'FAILED' if bad else 'passed'} ({len(cases)} models, {refac} of them with more than 256 iterations, {bad} failures)")
sys.exit(1 if bad else 0)
