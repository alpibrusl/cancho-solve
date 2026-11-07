#!/usr/bin/env python3
"""Gate (docs/design.md section 21.3): the presolve of the sparse solver changes no answer, and removes what it should. Three parts.
(1) Hand-built models, each built for one reduction, with the exact numbers of rows and columns the presolve removes (`stats.presolve_rows`, `stats.presolve_columns`; absent means
none) and the objective: a redundant row, an infeasible row (by activity), a singleton row that fixes a column, a singleton row that makes the model infeasible, a fixed column, the chain
of the EV model (a charger row that cannot bind, then the `on` columns it blocked, then the link rows), a model with nothing to reduce, and a model reduced to nothing.
(2) 240 generated LPs full of the reducible structure (singleton rows, loose rows, fixed columns, free-cost columns, some made infeasible): `--method sparse` (presolve) and
`--method sparse-raw` (none) must agree with each other and with HiGHS (scipy) on status and objective (1e-6 relative), the printed solution must satisfy the expanded model
(1e-6) and `verified` must hold; and the presolve must have removed something on at least 90% of the optimal ones (a presolve that does nothing passes (1) only if it is wrong).
(3) The ample EV-depot models of docs/design.md 21.1 (48 x 24, 96 x 32, 144 x 40) with the same agreement, and at least 95% of the rows removed.
Usage: SOLVE=build/solve python3 scripts/check_presolve.py   (needs scipy)"""
import json, os, random, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hs import run_solve, highs, violation, objective_of
from evgen import generate

SOLVE = os.environ.get("SOLVE", "build/solve")
bad = 0


def fail(msg):
    global bad
    bad += 1
    print("FAIL " + msg)


def solve(text, method):
    # not through hs.run_solve: it appends --method $SOLVE_METHOD, and this gate compares two methods
    p = subprocess.run([SOLVE, "run", "--relax", "--method", method], input=text, capture_output=True, text=True)
    if p.returncode not in (0, 1):
        return None, p.stderr.strip()[:200]
    return json.loads(p.stdout), None


def removed(r):
    return r["stats"].get("presolve_rows", 0), r["stats"].get("presolve_columns", 0)


HAND = [
    ("redundant row", "var x : real 0..1;\nvar y : real 0..1;\nmaximize x + 2*y;\nsubject to\n    r: x + y <= 5;\n", "optimal", 3.0, (1, 2)),
    ("infeasible by activity", "var x : real 0..1;\nvar y : real 0..1;\nminimize x;\nsubject to\n    r: x + y >= 3;\n", "infeasible", None, None),
    ("singleton rows fix a column", "var x : real 0..10;\nvar y : real 0..10;\nmaximize y;\nsubject to\n    r1: 2*x >= 6;\n    r2: 2*x <= 6;\n    r3: x + y <= 5;\n", "optimal", 2.0, (3, 2)),
    ("singleton row infeasible", "var x : real 0..10;\nvar y : real 0..10;\nmaximize y;\nsubject to\n    r1: x >= 20;\n    r2: x + y <= 5;\n", "infeasible", None, None),
    ("fixed column", "var x : real 3..3;\nvar y : real 0..10;\nminimize y;\nsubject to\n    r: x + y <= 8;\n", "optimal", 0.0, (1, 2)),
    ("the chain of the EV model", "var c1 : real 0..11;\nvar c2 : real 0..11;\nvar o1 : real 0..1;\nvar o2 : real 0..1;\nminimize c1 + c2;\nsubject to\n"
     "    l1: c1 - 11*o1 <= 0;\n    l2: c2 - 11*o2 <= 0;\n    ch: o1 + o2 <= 2;\n    need: c1 + c2 >= 5;\n", "optimal", 5.0, (3, 2)),
    ("fixed column that no side lets go", "var x : real 3..3;\nvar y : real 0..10;\nminimize x + y;\nsubject to\n    r: x + y >= 5;\n", "optimal", 5.0, (1, 2)),
    ("nothing to reduce", "var x : real 0..10;\nvar y : real 0..10;\nmaximize 3*x + 2*y;\nsubject to\n    c1: x + y <= 4;\n    c2: x + 3*y <= 6;\n", "optimal", 12.0, (0, 0)),
    ("reduced to nothing", "var x : real 0..5;\nmaximize x;\nsubject to\n    r: x <= 10;\n", "optimal", 5.0, (1, 1)),
]
for name, text, status, obj, rc in HAND:
    for method in ("sparse", "sparse-raw"):
        r, err = solve(text, method)
        if r is None:
            fail(f"{name} ({method}): {err}")
            continue
        if r["status"] != status:
            fail(f"{name} ({method}): status {r['status']}, wanted {status}")
            continue
        if status == "optimal":
            if abs(r["objective"] - obj) > 1e-9 * (1 + abs(obj)) or not r["verified"]:
                fail(f"{name} ({method}): objective {r['objective']} (wanted {obj}), verified {r['verified']}")
            if method == "sparse" and removed(r) != rc:
                fail(f"{name}: the presolve removed (rows, columns) = {removed(r)}, wanted {rc}")
            if method == "sparse-raw" and removed(r) != (0, 0):
                fail(f"{name} (sparse-raw): presolve counts {removed(r)} where there is no presolve")


def reducible_lp(seed):
    r = random.Random(seed)
    n, m = r.randint(6, 28), r.randint(5, 24)
    lines, lo, hi = [], [], []
    for j in range(n):
        a = r.choice([0, 0, 0, 1, 2]) if r.random() < 0.7 else r.randint(0, 3)
        b = a if r.random() < 0.12 else a + r.randint(1, 9)
        lo.append(a)
        hi.append(b)
        lines.append(f"var v{j} : real {a}..{b};")
    cost = [r.choice([0, 0, 1, -1, 2, -3, 0.5]) for _ in range(n)]
    lines.append(("minimize " if r.random() < 0.5 else "maximize ") + " + ".join(f"{cost[j]}*v{j}" for j in range(n)) + ";")
    lines.append("subject to")
    x0 = [r.uniform(lo[j], hi[j]) for j in range(n)]
    for i in range(m):
        kind = r.random()
        k = 1 if kind < 0.3 else r.randint(2, 5)
        cols = r.sample(range(n), min(k, n))
        co = [r.choice([-3, -2, -1, 1, 2, 3]) for _ in cols]
        act = sum(c * x0[j] for c, j in zip(co, cols))
        amax = sum(c * (hi[j] if c > 0 else lo[j]) for c, j in zip(co, cols))
        amin = sum(c * (lo[j] if c > 0 else hi[j]) for c, j in zip(co, cols))
        sense = r.choice(["<=", ">=", "<="])
        if r.random() < 0.3:      # loose: cannot bind
            rhs = amax + r.randint(0, 3) if sense == "<=" else amin - r.randint(0, 3)
        elif r.random() < 0.08:   # contradictory on purpose
            rhs = amin - r.randint(1, 4) if sense == "<=" else amax + r.randint(1, 4)
        else:
            rhs = act + (r.uniform(0, 2) if sense == "<=" else -r.uniform(0, 2))
        lines.append(f"    r{i}: " + " + ".join(f"{c}*v{j}" for c, j in zip(co, cols)) + f" {sense} {round(rhs, 3)};")
    return "\n".join(lines).replace("+ -", "- ") + "\n"


reduced = optimal = 0
for seed in range(240):
    text = reducible_lp(seed)
    p, _ = run_solve(SOLVE, ["expand"], text)
    if p.returncode != 0:
        fail(f"generated {seed}: expand refused: {p.stderr.strip()[:200]}")
        continue
    model = json.loads(p.stdout)
    hstatus, hobj, _, _ = highs(model)
    a, ea = solve(text, "sparse")
    b, eb = solve(text, "sparse-raw")
    if a is None or b is None:
        fail(f"generated {seed}: {ea or eb}")
        continue
    if hstatus == 2:
        if a["status"] != "infeasible" or b["status"] != "infeasible":
            fail(f"generated {seed}: HiGHS infeasible, presolve says {a['status']}, raw says {b['status']}")
        continue
    if hstatus != 0:
        continue
    optimal += 1
    for tag, r in (("presolve", a), ("raw", b)):
        if r["status"] != "optimal":
            fail(f"generated {seed}: HiGHS optimal {hobj}, {tag} says {r['status']}")
            break
        if abs(r["objective"] - hobj) > 1e-6 * (1 + abs(hobj)):
            fail(f"generated {seed}: {tag} objective {r['objective']} against HiGHS {hobj}")
            break
        v = violation(model, r["x"])
        if v > 1e-6 or not r["verified"]:
            fail(f"generated {seed}: {tag} solution violates the model by {v}, verified {r['verified']}")
            break
        if abs(objective_of(model, r["x"]) - r["objective"]) > 1e-6 * (1 + abs(hobj)):
            fail(f"generated {seed}: {tag} printed objective is not that of the printed solution")
            break
    else:
        if removed(a) != (0, 0):
            reduced += 1
if optimal and reduced < 0.9 * optimal:
    fail(f"the presolve removed something on only {reduced} of {optimal} optimal generated models")

for V, T in ((48, 24), (96, 32), (144, 40)):
    text = generate(V, T, "ample", 7)
    a, ea = solve(text, "sparse")
    b, eb = solve(text, "sparse-raw")
    if a is None or b is None:
        fail(f"EV {V}x{T}: {ea or eb}")
        continue
    if a["status"] != "optimal" or b["status"] != "optimal" or abs(a["objective"] - b["objective"]) > 1e-6 * (1 + abs(b["objective"])) or not a["verified"]:
        fail(f"EV {V}x{T}: presolve {a['status']} {a.get('objective')} verified {a.get('verified')}, raw {b['status']} {b.get('objective')}")
        continue
    rows = a["stats"]["rows"]
    if removed(a)[0] < 0.95 * rows:
        fail(f"EV {V}x{T}: only {removed(a)[0]} of {rows} rows removed")
    if a["stats"]["iterations"] * 2 > b["stats"]["iterations"]:
        fail(f"EV {V}x{T}: iterations {a['stats']['iterations']} with the presolve against {b['stats']['iterations']} without: less than a factor of 2")

print(f"presolve gate: {'FAILED' if bad else 'passed'} ({len(HAND)} hand models, 240 generated of which {optimal} optimal and {reduced} reduced, 3 EV models, {bad} failures)")
sys.exit(1 if bad else 0)
