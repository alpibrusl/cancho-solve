#!/usr/bin/env python3
"""Gate (docs/design.md 19.8): the implied cuts through variable upper bounds never change an answer, and they do what is claimed.
1. validity: on generated EV-depot instances (ample, tight and impossible chargers; several seeds), facility-location instances (the other big-M shape, with equal and with varied bounds) and 60
   random big-M models with every row shape the generator reads or refuses (`mixed`), the status and
   the optimal value with the cuts equal those without (`--experiment 8`) and HiGHS's (scipy milp on `solve expand`), to 1e-6 relative; the incumbent `solve verify` accepts.
2. effect: docs/examples/ev_depot_3.sol adds 6 cuts and takes exactly 3,724 nodes (47,105 without), and its root bound rises from 26.58 to at least 27.2; a knapsack, which has no variable
   upper bound, gets 0 cuts; `--experiment 8` gives 0 cuts; and the number of cuts added on the generated instances and the sum of their root bounds are held exactly (a weaker or a stronger
   cut moves them).
Needs scipy. Usage: SOLVE=build/solve python3 scripts/check_cuts.py"""
import json, os, random, subprocess, sys
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate

SOLVE = os.environ.get("SOLVE", "build/solve")
fails = []
skipped = []
checks = 0


def sh(argv, text):
    return subprocess.run([SOLVE] + argv, input=text, capture_output=True, text=True, timeout=120)


def solve(text, extra=()):
    p = sh(["run"] + list(extra), text)
    try:
        return json.loads(p.stdout), p.returncode
    except json.JSONDecodeError:
        return {"status": "error:" + p.stderr[:80]}, p.returncode


def highs(text):
    ex = json.loads(sh(["expand"], text).stdout)
    n = len(ex["variables"])
    c = np.zeros(n)
    for j, a in ex["objective"]["terms"]:
        c[j] += a
    sign = -1.0 if ex["objective"]["sense"] == "maximize" else 1.0
    ri, ci, vs, lo, hi = [], [], [], [], []
    for r, row in enumerate(ex["constraints"]):
        for j, a in row["terms"]:
            ri.append(r); ci.append(j); vs.append(a)
        s, b = row["sense"], row["rhs"]
        lo.append(b if s in (">=", "==") else -np.inf)
        hi.append(b if s in ("<=", "==") else np.inf)
    A = coo_matrix((vs, (ri, ci)), shape=(len(ex["constraints"]), n)).tocsr()
    r = milp(sign * c, constraints=LinearConstraint(A, lo, hi), integrality=np.array([1 if v["kind"] in ("bool", "int") else 0 for v in ex["variables"]]),
             bounds=Bounds([v["lo"] for v in ex["variables"]], [v["hi"] for v in ex["variables"]]), options={"time_limit": 60})
    if r.status == 0:
        return "optimal", sign * r.fun + ex["objective"]["constant"]
    return ("infeasible" if r.status == 2 else "other"), None


def facility(F, C, seed, varied=False):
    """Facility location: open[f] bool, ship[f,c] real, ship <= demand * open, demands met, capacities; the big-M shape of design.md 19.8."""
    rng = random.Random(seed)
    d = [rng.randint(3, 9) for _ in range(C)]
    cap = [rng.randint(8, 16) for _ in range(F)]
    fixed = [rng.randint(5, 20) for _ in range(F)]
    cost = [rng.randint(1, 6) for _ in range(F * C)]
    lim = [rng.randint(3, 9) for _ in range(F * C)] if varied else [d[c] for f in range(F) for c in range(C)]
    return f"""param F = {F};
param C = {C};
param d = {d};
param cap = {cap};
param fixed = {fixed};
param cost = {cost};
param lim = {lim};
var open[0..F] : bool;
var ship[0..F, 0..C] : real 0..20;
minimize total: sum f in 0..F: fixed[f] * open[f] + sum f in 0..F: sum c in 0..C: cost[f*C+c] * ship[f,c];
subject to
    forall c in 0..C: demand: sum f in 0..F: ship[f,c] >= d[c];
    forall f in 0..F: forall c in 0..C: vub: ship[f,c] <= lim[f*C+c] * open[f];
    forall f in 0..F: capacity: sum c in 0..C: ship[f,c] <= cap[f] * open[f];
"""


def mixed(seed):
    """A random big-M model with every shape the cut generator reads or must refuse (docs/design.md 19.8): variable upper bounds written four ways, one with a right side and one that is not one, two on
    the same column, covering rows over linked, plain and negative terms in both senses, a row over one linked column, and an integer column with a negative lower bound."""
    rng = random.Random(1000 + seed)
    K = rng.randint(3, 5)
    lines = [f"var y[0..{K}] : bool;", f"var x[0..{K}] : real 0..10;", "var z : real 0..4;", "var k : int -2..3;", "var h : int 0..3;", "var u : real -4..6;"]
    rows = []
    for i in range(K):
        q = rng.randint(3, 10)
        style = rng.choice("ABCDEA")
        if style == "A":
            rows.append(f"v{i}: x[{i}] - {q}*y[{i}] <= 0;")
        elif style == "B":
            rows.append(f"v{i}: {q}*y[{i}] - x[{i}] >= 0;")
        elif style == "C":
            rows.append(f"v{i}: x[{i}] - {q}*y[{i}] <= {rng.randint(1, 2)};")
        elif style == "D":
            rows.append(f"v{i}: x[{i}] + {q}*y[{i}] <= {rng.randint(0, 3)};")
        else:
            j = rng.randrange(K)
            rows.append(f"v{i}: x[{i}] - {q}*y[{i}] <= 0;")
            rows.append(f"w{i}: x[{i}] - {rng.randint(2, 12)}*y[{j}] <= 0;")
    xs = " + ".join(f"{rng.randint(1, 3)}*x[{i}]" for i in range(K))
    b = rng.randint(4, 14)
    rows.append(f"cover: {xs} + z >= {b};")
    rows.append(f"cover_neg: x[0] + x[1] - k >= {rng.randint(-1, 4)};")
    rows.append(f"cover_le: -x[0] - x[{K - 1}] - 2*z <= -{rng.randint(1, 6)};")
    rows.append(f"single: x[{K - 1}] >= {rng.randint(1, 3)};")
    rows.append(f"mix: x[0] + y[1] + y[2] + h >= {rng.randint(2, 6)};")
    rows.append(f"pair0: x[0] + {rng.randint(2, 5)}*y[0] + x[1] >= {rng.randint(2, 8)};")
    rows.append(f"pair1: x[1] + {rng.randint(2, 5)}*y[1] + x[2] >= {rng.randint(2, 8)};")
    rows.append(f"onecol: x[0] + y[0] >= {rng.randint(1, 3)};")
    if rng.random() < 0.7:
        rows.append(f"vk: x[2] - {rng.randint(2, 5)}*k <= 0;")
    rows.append(f"ck: x[0] + x[1] + {rng.randint(1, 3)}*k >= {rng.randint(0, 6)};")
    if K >= 4:
        rows.append(f"vu: u + {rng.randint(2, 4)}*y[3] <= 0;")
        rows.append(f"covu: u + {rng.randint(5, 8)}*y[3] + x[0] >= {rng.randint(0, 3)};")
    rows.append(f"cap: " + " + ".join(f"y[{i}]" for i in range(K)) + f" <= {max(1, K - rng.randint(0, 2))};")
    obj = " + ".join([f"{rng.randint(1, 4)}*x[{i}]" for i in range(K)] + [f"{rng.randint(1, 9)}*y[{i}]" for i in range(K)] + [f"{rng.randint(1, 3)}*z", f"{rng.randint(-2, 3)}*k", f"{rng.randint(0, 2)}*h", f"{rng.randint(1, 2)}*u"])
    return "\n".join(lines) + f"\nminimize total: {obj};\nsubject to\n    " + "\n    ".join(rows) + "\n"


def agree(a, b):
    return a is not None and b is not None and abs(a - b) <= 1e-6 * (1 + abs(b))


def validity(name, text):
    global checks
    checks += 1
    with_cuts, _ = solve(text)
    if with_cuts["status"] in ("feasible", "unknown"):   # the search ran into its node limit: nothing to compare
        skipped.append(name)
        return with_cuts
    without, _ = solve(text, ["--experiment", "8"])
    hs, hv = highs(text)
    ok = with_cuts["status"] == without["status"] == hs
    if ok and hs == "optimal":
        ok = agree(with_cuts["objective"], hv) and agree(without["objective"], hv)
        v = sh(["verify"], text + "---\n" + json.dumps(with_cuts))
        ok = ok and v.returncode == 0
    if not ok:
        fails.append(f"{name}: with cuts {with_cuts.get('status')} {with_cuts.get('objective')}, without {without.get('status')} {without.get('objective')}, HiGHS {hs} {hv}")
    return with_cuts


ncut = 0
for setting in ("ample", "tight"):
    for V, T in ((3, 6), (4, 6), (5, 7), (6, 8)):
        for seed in (1, 2, 3):
            r = validity(f"ev {setting} {V}x{T} seed {seed}", generate(V, T, setting, seed))
            ncut += r.get("stats", {}).get("cuts", 0)
# chargers too few: V=5 vehicles, 1 charger, long needs: impossible; and a tight one
validity("ev impossible", open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "examples", "ev_depot_2.sol")).read())
for F, C in ((3, 4), (4, 5), (5, 6)):
    for seed in range(1, 6):
        for varied in (False, True):
            r = validity(f"facility {F}x{C} seed {seed}{' varied' if varied else ''}", facility(F, C, seed, varied))
            ncut += r.get("stats", {}).get("cuts", 0)
rootsum = 0.0
for seed in range(1, 61):
    r = validity(f"mixed seed {seed}", mixed(seed))
    ncut += r.get("stats", {}).get("cuts", 0)
    if r["status"] == "optimal":
        rb, _ = solve(mixed(seed), ["--node-limit", "1"])
        rootsum += rb.get("bound", rb.get("objective", 0.0))
if len(skipped) > 4:
    fails.append(f"{len(skipped)} instances hit the node limit: {skipped}")
EXPECTED_CUTS = 539; ROOT_SUM = 608.9876   # measured once (python3 scripts/check_cuts.py --print): the total number of cuts added on the generated instances, held exactly
if "--print" in sys.argv:
    print("EXPECTED_CUTS =", ncut, " ROOT_SUM =", round(rootsum, 4))
elif ncut != EXPECTED_CUTS or abs(rootsum - ROOT_SUM) > 1e-3:
    fails.append(f"{ncut} cuts added on the generated instances (exactly {EXPECTED_CUTS} expected), sum of root bounds {rootsum:.4f} (expected {ROOT_SUM})")
if ncut == 0:
    fails.append("no instance got a cut: the gate cannot fail")

here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ev3 = open(os.path.join(here, "docs", "examples", "ev_depot_3.sol")).read()
r, _ = solve(ev3)
checks += 1
if r["stats"]["cuts"] != 6 or r["stats"]["nodes"] != 3724 or abs(r["objective"] - 27.56) > 1e-6:
    fails.append(f"ev_depot_3: cuts {r['stats']['cuts']} (6), nodes {r['stats']['nodes']} (3724), objective {r.get('objective')}")
root, _ = solve(ev3, ["--node-limit", "1"])
roff, _ = solve(ev3, ["--node-limit", "1", "--experiment", "8"])
checks += 1
if not (root.get("bound", 0) >= 27.2 and roff.get("bound", 0) <= 26.6):
    fails.append(f"root bound with cuts {root.get('bound')} (>= 27.2), without {roff.get('bound')} (<= 26.6)")
checks += 1
r8, _ = solve(ev3, ["--experiment", "8"])
if r8["stats"]["cuts"] != 0:
    fails.append("--experiment 8 still adds cuts")
knap = open(os.path.join(here, "tests", "ok", "knapsack.sol")).read()
r, _ = solve(knap)
checks += 1
if r["stats"]["cuts"] != 0:
    fails.append(f"knapsack got {r['stats']['cuts']} cuts")

for f in fails:
    print("FAIL", f)
print(f"cuts gate: {'passed' if not fails else 'FAILED'} ({checks} checks, {ncut} cuts added on the generated instances, {len(skipped)} skipped at the node limit, {len(fails)} failures)")
sys.exit(1 if fails else 0)
