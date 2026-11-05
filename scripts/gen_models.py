"""Model generators and the HiGHS oracle shared by scripts/check_cuts.py and scripts/check_mir.py (docs/design.md 19.8 and 21.2): `facility`, `mixed`, `highs`, `solve`, `sh`."""
import json, os, random, subprocess
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

SOLVE = os.environ.get("SOLVE", "build/solve")


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
