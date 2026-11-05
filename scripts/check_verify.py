#!/usr/bin/env python3
"""Gate 8 (docs/design.md section 20.5): `solve verify`, which must accept what is feasible and refuse what is not, with the right rule tag.

1. Accept: `solve run`'s own output on tests/ok, tests/mip and generated models (LP, MIP, assignment, knapsack, set cover), and HiGHS's optimum for the generated ones, verify.
   The Python evaluator below works from the JSON of `solve expand` (not from the layout the binary uses) and must agree on the verdict and on the maximum violations (1e-9).
2. Refuse: single faults made to each accepted solution: a bound broken, a row broken, an integer made fractional, the claimed objective changed. Each is refused with its tag
   as `error` (exit 2, nothing on standard output); a fault that does not apply to a model is skipped and counted.
3. Shape: missing and unknown variables, a duplicate key, a non-object solution, no separator, an infeasible result, a model `check` refuses, bad flags, `--tolerance`.
Usage: SOLVE=build/solve python3 scripts/check_verify.py [--quick]"""
import glob, json, os, random, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import build

SOLVE = os.environ.get("SOLVE", "build/solve")
QUICK = "--quick" in sys.argv
bad = 0
checks = 0
skipped = {"bound": 0, "row": 0, "integrality": 0}
counts = {"accepted": 0, "bound": 0, "row": 0, "integrality": 0, "objective": 0, "highs": 0}

def fail(msg):
    global bad
    bad += 1
    print("FAIL " + msg)

def call(args, data):
    p = subprocess.run([SOLVE, *args], input=data, capture_output=True, timeout=120)
    return p

def verify(model_text, sol, args=()):
    """-> (exit status, parsed stdout or None, parsed stderr or None)"""
    body = sol if isinstance(sol, str) else json.dumps(sol)
    p = call(["verify", *args], (model_text + "\n---\n" + body).encode())
    out = json.loads(p.stdout) if p.stdout else None
    err = json.loads(p.stderr) if p.stderr else None
    return p.returncode, out, err

# ---- the Python evaluator, from the expanded model only
def evaluate(model, x, tol=1e-6):
    """-> (first violated tag or None, dict of the maximum violations in the scales of docs/design.md 20.3), the objective"""
    import math
    vals = [x[v["name"]] for v in model["variables"]]
    mb = mi = mr = 0.0
    tags = []
    for v, xv in zip(model["variables"], vals):
        mb = max(mb, (v["lo"] - xv) / (1 + abs(v["lo"])), (xv - v["hi"]) / (1 + abs(v["hi"])))
        if v["kind"] != "real":
            mi = max(mi, abs(xv - round(xv)))
    for row in model["constraints"]:
        act = math.fsum(a * vals[j] for j, a in row["terms"])
        mag = math.fsum(abs(a * vals[j]) for j, a in row["terms"])
        d = act - row["rhs"]
        d = d if row["sense"] == "<=" else (-d if row["sense"] == ">=" else abs(d))
        mr = max(mr, d / (1 + max(abs(row["rhs"]), mag)))
    obj = model["objective"]
    ev = 0.0 if obj is None else obj["constant"] + math.fsum(a * vals[j] for j, a in obj["terms"])
    if mb > tol:
        tags.append("solve.bound-violated")
    if mi > tol:
        tags.append("solve.not-integral")
    if mr > tol:
        tags.append("solve.row-violated")
    return (tags[0] if tags else None), {"max_bound_violation": max(mb, 0.0), "max_integrality_violation": mi, "max_row_violation": max(mr, 0.0)}, ev

def check_accept(name, text, model, sol):
    """The solution `sol` (a dict with x and objective) is feasible: the binary says verified, and agrees with the Python evaluator."""
    global checks
    checks += 1
    code, out, err = verify(text, sol)
    tag, mx, ev = evaluate(model, sol["x"])
    if tag is not None:
        fail(f"{name}: the Python evaluator rejects the solution ({tag}): the test input is wrong")
        return False
    if code != 0 or out is None or out.get("status") != "verified":
        fail(f"{name}: not verified: exit {code} {err}")
        return False
    for k, v in mx.items():
        if abs(out[k] - v) > 1e-9 * (1 + abs(v)):
            fail(f"{name}: {k} {out[k]}, the Python evaluator says {v}")
    if abs(out["objective"] - ev) > 1e-9 * (1 + abs(ev)):
        fail(f"{name}: objective {out['objective']}, the Python evaluator says {ev}")
    if out.get("objective_checked") is not True or out["variables"] != len(model["variables"]) or out["rows"] != len(model["constraints"]):
        fail(f"{name}: wrong counts or objective_checked in {out}")
    if out["tolerance"] != 1e-6:
        fail(f"{name}: tolerance {out['tolerance']}")
    return True

def expect_refusal(name, text, sol, tag, args=()):
    global checks
    checks += 1
    code, out, err = verify(text, sol, args)
    if code != 2 or out is not None or err is None or err.get("error") != tag:
        fail(f"{name}: wanted exit 2 with {tag}, got exit {code}, stdout {out}, stderr {err}")
        return None
    if tag.split(".")[1] in ("bound-violated", "not-integral", "row-violated", "objective-mismatch"):
        v = err.get("violations")
        if not v or v[0].get("rule") != tag or err.get("count", 0) < len(v) or "what" not in v[0]:
            fail(f"{name}: the violations list is wrong: {err}")
    return err

def faults(name, text, model, sol, rng):
    vs = model["variables"]
    x = sol["x"]
    # 1. a bound broken: one variable past its upper bound, one below its lower
    j = rng.randrange(len(vs))
    y = dict(x); y[vs[j]["name"]] = vs[j]["hi"] + 1 + rng.random() * 3
    expect_refusal(f"{name} bound hi", text, {**sol, "x": y}, "solve.bound-violated"); counts["bound"] += 1
    j = rng.randrange(len(vs))
    y = dict(x); y[vs[j]["name"]] = vs[j]["lo"] - 1 - rng.randrange(3)
    expect_refusal(f"{name} bound lo", text, {**sol, "x": y}, "solve.bound-violated"); counts["bound"] += 1
    # 2. a row broken, by a move inside the bounds that keeps integer columns whole, found with the evaluator
    done = False
    order = list(range(len(model["constraints"])))
    rng.shuffle(order)
    for r in order:
        for jj, _a in model["constraints"][r]["terms"]:
            for target in (vs[jj]["lo"], vs[jj]["hi"]):
                y = dict(x); y[vs[jj]["name"]] = float(target)
                tag, mx, _ = evaluate(model, y)
                if tag == "solve.row-violated" and mx["max_row_violation"] > 1e-3 and not done:
                    expect_refusal(f"{name} row", text, {**sol, "x": y}, "solve.row-violated"); counts["row"] += 1
                    done = True
        if done:
            break
    if not done:
        skipped["row"] += 1
    # 3. an integer made fractional (inside the bounds, so integrality is the first thing wrong)
    ints = [v for v in vs if v["kind"] != "real" and v["hi"] > v["lo"]]
    if ints:
        v = rng.choice(ints)
        y = dict(x)
        y[v["name"]] = x[v["name"]] + 0.5 if x[v["name"]] + 0.5 <= v["hi"] else x[v["name"]] - 0.5
        expect_refusal(f"{name} integrality", text, {**sol, "x": y}, "solve.not-integral"); counts["integrality"] += 1
    else:
        skipped["integrality"] += 1
    # 4. the claimed objective changed
    ev = sol["objective"]
    for bump in (1.0, 1e-3 * (1 + abs(ev)), -(1e-3 * (1 + abs(ev)))):
        expect_refusal(f"{name} objective {bump}", text, {**sol, "objective": ev + bump}, "solve.objective-mismatch"); counts["objective"] += 1
    # and the objective left out: accepted, and reported as not compared
    code, out, err = verify(text, {"x": x})
    if code != 0 or out.get("objective_checked") is not False:
        fail(f"{name}: without a claimed objective: exit {code} {out} {err}")

def run_solution(text):
    p = call(["run"], text.encode())
    if p.returncode != 0:
        return None
    r = json.loads(p.stdout)
    return r if r.get("status") == "optimal" else None

def highs_x(model):
    import numpy as np
    from scipy.optimize import milp, LinearConstraint, Bounds
    c, A_ub, b_ub, A_eq, b_eq, bounds, const, sign = build(model)
    cons = []
    if A_ub is not None:
        cons.append(LinearConstraint(A_ub, -np.inf, b_ub))
    if A_eq is not None:
        cons.append(LinearConstraint(A_eq, b_eq, b_eq))
    integ = np.array([0 if v["kind"] == "real" else 1 for v in model["variables"]])
    res = milp(c, constraints=cons, integrality=integ, bounds=Bounds([b[0] for b in bounds], [b[1] for b in bounds]), options={"mip_rel_gap": 0.0})
    if res.x is None:
        return None
    xs = {v["name"]: float(round(res.x[i])) if v["kind"] != "real" else float(res.x[i]) for i, v in enumerate(model["variables"])}
    return {"x": xs, "objective": sign * float(res.fun) + const}

rng = random.Random(20261105)

# ---- 1 and 2: hand-written and generated models
cases = []
for path in sorted(glob.glob("tests/ok/*.sol") + glob.glob("tests/mip/*.sol")):
    cases.append((path, open(path).read()))
for s in range(14):
    cases.append((f"lp {s}", lpgen.random_lp(s, 2 + s % 6, 2 + s % 7, 0.6)))
for s in range(14):
    cases.append((f"mip {s}", lpgen.random_mip(s, 2 + s % 5, 2 + s % 5, 0.7, 1.0)))
for s in range(14):
    cases.append((f"mixed {s}", lpgen.random_mip(500 + s, 3 + s % 6, 3 + s % 7, 0.6, 0.5)))
for s in range(8):
    cases.append((f"assignment {s}", lpgen.assignment(s, 3 + s)))
for s in range(8):
    cases.append((f"knapsack {s}", lpgen.knapsack(s, 8 + 2 * s)))
for s in range(8):
    cases.append((f"set cover {s}", lpgen.set_cover(s, 8 + s, 10 + s, 0.2)))
if QUICK:
    cases = cases[::4]

for name, text in cases:
    q = call(["expand"], text.encode())
    if q.returncode != 0:
        continue                           # tests/ok may hold models that only check
    model = json.loads(q.stdout)
    sol = run_solution(text)
    if sol is None:
        continue
    counts["accepted"] += 1
    # `run`'s output verbatim (with every extra member), then the bare form
    if not check_accept(name + " (run output)", text, model, sol):
        continue
    check_accept(name + " (bare)", text, model, {"x": sol["x"], "objective": sol["objective"]})
    faults(name, text, model, sol, rng)
    if not name.startswith("tests/") and len(model["variables"]) <= 40:
        h = highs_x(model)
        if h is not None:
            counts["highs"] += 1
            check_accept(name + " (HiGHS)", text, model, h)

# ---- 3: shape
LP = open("tests/ok/lp_basic.sol").read()
good = json.loads(call(["run"], LP.encode()).stdout)
def refuse(name, text, body, tag, args=()):
    return expect_refusal(name, text, body, tag, args)

refuse("missing variable", LP, {"x": {"x": 1.0}}, "solve.missing-variable")
e = refuse("unknown variable", LP, {"x": {"x": 1.0, "y": 1.0, "z": 0.0}}, "solve.unknown-variable")
if e and "z" not in e.get("message", ""):
    fail(f"unknown variable: the message does not name it: {e}")
refuse("duplicate key", LP, '{"x":{"x":1.0,"y":1.0,"y":1.0}}', "solve.bad-solution")
refuse("not an object", LP, "[1,2]", "solve.bad-solution")
refuse("x not an object", LP, {"x": [1, 2]}, "solve.bad-solution")
refuse("x holds a string", LP, {"x": {"x": "1", "y": 1}}, "solve.bad-solution")
refuse("not json", LP, "{x:", "solve.bad-solution")
refuse("empty", LP, "", "solve.bad-solution")
refuse("an infeasible result", LP, {"status": "infeasible", "stats": {}}, "solve.bad-solution")
refuse("objective not a number", LP, {"x": good["x"], "objective": "3"}, "solve.bad-solution")
# unordered keys are found by name
rev = {"x": dict(reversed(list(good["x"].items()))), "objective": good["objective"]}
check_accept("reversed keys", LP, json.loads(call(["expand"], LP.encode()).stdout), rev)
# no separator, and a separator that is not alone on its line
p = call(["verify"], LP.encode())
if p.returncode != 2 or json.loads(p.stderr)["error"] != "solve.bad-solution":
    fail(f"no separator: {p.returncode} {p.stderr}")
p = call(["verify"], (LP + "x---\n" + json.dumps(good)).encode())
if p.returncode != 2 or json.loads(p.stderr)["error"] != "solve.bad-solution":
    fail(f"separator not alone on its line: {p.returncode} {p.stderr}")
# a model that check refuses is refused with check's tag
p = call(["verify"], b"var x : real 0..1;\nminimize x*x;\n---\n{}")
if p.returncode != 2 or json.loads(p.stderr)["error"] != "solve.nonlinear" or p.stdout:
    fail(f"refused model: {p.returncode} {p.stderr}")
# a CRLF separator line is accepted (the model and the solution may come from a Windows tool)
p = call(["verify"], (LP + "\r\n---\r\n" + json.dumps(good)).encode())
if p.returncode != 0:
    fail(f"CRLF separator: {p.returncode} {p.stderr}")
# flags
for args in (["--tolerance"], ["--tolerance", "x"], ["--tolerance", "-1"], ["--tolerance", "0.5"], ["--bogus"], ["--tolerance", "1e-6", "--tolerance"]):
    p = call(["verify", *args], (LP + "\n---\n" + json.dumps(good)).encode())
    if p.returncode != 2 or json.loads(p.stderr)["error"] != "solve.usage":
        fail(f"flags {args}: {p.returncode} {p.stderr}")
# tolerance: a row off by 1e-7 (c1: x + y <= 4, scale 1 + max(4, |act|) = 5 at the optimum, so a violation of 5e-7 is inside 1e-6)
tight = dict(good["x"]); tight["x"] = good["x"]["x"] + 5e-7
model_lp = json.loads(call(["expand"], LP.encode()).stdout)
c_obj = 3 * tight["x"] + 2 * tight["y"]
sol_t = {"x": tight, "objective": c_obj}
tag, mx, _ = evaluate(model_lp, tight)
if tag is not None:
    fail(f"tolerance test: the evaluator rejects at 1e-6: {tag} {mx}")
check_accept("inside the default tolerance", LP, model_lp, sol_t) if tag is None else None
expect_refusal("tolerance 1e-9", LP, sol_t, "solve.row-violated", ("--tolerance", "1e-9"))
loose = dict(good["x"]); loose["x"] = good["x"]["x"] + 5e-5
sol_l = {"x": loose, "objective": 3 * loose["x"] + 2 * loose["y"]}
expect_refusal("5e-5 at the default", LP, sol_l, "solve.row-violated")
code, out, err = verify(LP, sol_l, ("--tolerance", "1e-3"))
if code != 0 or out["tolerance"] != 1e-3:
    fail(f"5e-5 at 1e-3: {code} {out} {err}")
code, out, err = verify(LP, {"x": good["x"], "objective": good["objective"]}, ("--tolerance", "0"))
if code != 0:
    fail(f"tolerance 0 on an exact solution: {code} {out} {err}")
# several violations are all listed, the first kind is the tag
bad_x = {"x": 11.0, "y": 11.0}
e = expect_refusal("several faults", LP, {"x": bad_x, "objective": 0.0}, "solve.bound-violated")
if e and (e["count"] < 5 or {v["rule"] for v in e["violations"]} != {"solve.bound-violated", "solve.row-violated", "solve.objective-mismatch"}):
    fail(f"several faults: {e}")

# ---- 4: the edges of the tolerances (docs/design.md 20.3), one variable at a time, at the default 1e-6
def edge(name, decl, x, want, extra="", rows=""):
    """a model with the variable declaration `decl` (named v), the claimed value x: want None for verified, else the tag"""
    text = f"{decl}\n{extra}subject to\n    c: v >= -1e9;\n{rows}"
    m = json.loads(call(["expand"], text.encode()).stdout)
    sol = {"x": {"v": x}}
    if want is None:
        tag, mx, ev = evaluate(m, sol["x"])
        if tag is not None:
            fail(f"edge {name}: the evaluator says {tag}")
            return
        sol["objective"] = ev
        check_accept(f"edge {name}", text, m, sol)
    else:
        expect_refusal(f"edge {name}", text, sol, want)

edge("lo scale 1, inside", "var v : real 0..1;", -5e-7, None)
edge("lo scale 1, outside", "var v : real 0..1;", -2e-6, "solve.bound-violated")
edge("hi scale 1, inside", "var v : real 0..1;", 1 + 5e-7, None)
edge("hi scale 1, outside", "var v : real 0..1;", 1 + 2e-6, "solve.bound-violated")
edge("hi scale 1001, inside", "var v : real 0..1000;", 1000 + 8e-4, None)
edge("hi scale 1001, outside", "var v : real 0..1000;", 1000 + 2e-3, "solve.bound-violated")
edge("lo scale 1001, inside", "var v : real -1000..0;", -1000 - 8e-4, None)
edge("lo scale 1001, outside", "var v : real -1000..0;", -1000 - 2e-3, "solve.bound-violated")
edge("lo=0 scale not inflated", "var v : real 0..1000;", -5e-6, "solve.bound-violated")
edge("int just below whole, inside", "var v : int 0..9;", 3 - 5e-7, None)
edge("int just above whole, inside", "var v : int 0..9;", 3 + 5e-7, None)
edge("int just above whole, outside", "var v : int 0..9;", 3 + 5e-5, "solve.not-integral")
edge("int just below whole, outside", "var v : int 0..9;", 3 - 5e-5, "solve.not-integral")
edge("int a third", "var v : int 0..9;", 3.3, "solve.not-integral")
edge("int two thirds", "var v : int 0..9;", 3.7, "solve.not-integral")
edge("bool a hundredth", "var v : bool;", 0.01, "solve.not-integral")
edge("bool just inside", "var v : bool;", 1e-7, None)
edge("real is not rounded", "var v : real 0..9;", 3.3, None)
edge("large int value is whole", "var v : int 0..1000000000;", 999999999.0, None)
# rows: the scale is 1 + max(|rhs|, sum |a x|)
for sense, a, rhs, x, ok in [("<=", 1, 0, 5e-7, True), ("<=", 1, 0, 5e-6, False), (">=", 1, 0, -5e-7, True), (">=", 1, 0, -5e-6, False),
                             ("==", 1, 0, 5e-7, True), ("==", 1, 0, -5e-7, True), ("==", 1, 0, 5e-6, False), ("==", 1, 0, -5e-6, False),
                             ("<=", 1, 1000, 1000 + 8e-4, True), ("<=", 1, 1000, 1000 + 2e-3, False), ("<=", 1, 0, 0.0, True),
                             ("<=", 1000, 0, 4e-10, True), ("<=", 1000, 0, 4e-8, False), ("==", 1, 0, 0.0, True)]:
    text = f"var v : real -1e6..1e6;\nsubject to\n    r: {a}*v {sense} {rhs};\n"
    m = json.loads(call(["expand"], text.encode()).stdout)
    if ok:
        tag, mx, ev = evaluate(m, {"v": x})
        if tag is not None:
            fail(f"row edge {sense} {a} {rhs} {x}: the evaluator says {tag}")
        else:
            check_accept(f"row edge {sense} {a} {rhs} {x}", text, m, {"x": {"v": x}, "objective": ev})
    else:
        expect_refusal(f"row edge {sense} {a} {rhs} {x}", text, {"x": {"v": x}}, "solve.row-violated")
# a big cancellation is not rounding noise: 1e8 - 1e8 + 3 == 3
text = "var a : real -1e9..1e9;\nvar b : real -1e9..1e9;\nvar c : real -1e9..1e9;\nsubject to\n    r: a + b + c == 3;\n"
m = json.loads(call(["expand"], text.encode()).stdout)
check_accept("cancellation", text, m, {"x": {"a": 1e8, "b": -1e8, "c": 3.0}, "objective": 0.0})
# ... and the same scale means a row of huge cancelling terms is allowed 1e-6 of their size: a violation of 50 among terms of 1e8 passes, 500 does not (docs/design.md 20.3)
check_accept("big terms, small violation", text, m, {"x": {"a": 1e8, "b": -1e8, "c": 53.0}, "objective": 0.0}) if evaluate(m, {"a": 1e8, "b": -1e8, "c": 53.0})[0] is None else fail("evaluator: 50 among 1e8")
expect_refusal("big terms, large violation", text, {"x": {"a": 1e8, "b": -1e8, "c": 503.0}, "objective": 0.0}, "solve.row-violated")
# compensated summation: 1e16 + 1 - 1e16 == 1 exactly, which a plain sum gets wrong; visible only at --tolerance 0
text = "var a : real -1e17..1e17;\nvar b : real -1e17..1e17;\nvar c : real -1e17..1e17;\nsubject to\n    r: a + b + c == 1;\n"
code, out, err = verify(text, {"x": {"a": 1e16, "b": 1.0, "c": -1e16}}, ("--tolerance", "0"))
if code != 0:
    fail(f"compensated sum at tolerance 0: {code} {err}")
# the objective tolerance is relative: 0.5 off at 1e6 passes, 0.5 off at 1000 does not
for scale, off, ok in [(1e6, 0.5, True), (1e6, 5.0, False), (1000.0, 0.5, False), (1000.0, 5e-4, True), (0.0, 5e-7, True), (0.0, 5e-6, False)]:
    text = f"var a : real 0..1e7;\nminimize a;\nsubject to\n    r: a >= {scale};\n"
    if ok:
        check_accept(f"objective {scale} off by {off}", text, json.loads(call(["expand"], text.encode()).stdout), {"x": {"a": scale}, "objective": scale + off}) if False else None
        code, out, err = verify(text, {"x": {"a": scale}, "objective": scale + off})
        if code != 0:
            fail(f"objective tolerance {scale} {off}: {code} {err}")
    else:
        expect_refusal(f"objective {scale} off by {off}", text, {"x": {"a": scale}, "objective": scale + off}, "solve.objective-mismatch")
# noise inside the tolerance on generated solutions: accepted, and the reported maxima are the evaluator's
noisy = 0
for name, text in cases[::3]:
    q = call(["expand"], text.encode())
    if q.returncode != 0:
        continue
    model = json.loads(q.stdout)
    sol = run_solution(text)
    if sol is None:
        continue
    y = {}
    for v in model["variables"]:
        e = rng.choice([-3e-7, 3e-7, 0.0])
        y[v["name"]] = sol["x"][v["name"]] + (e if v["kind"] != "real" or rng.random() < 0.5 else 0.0) * rng.random()
    tag, mx, ev = evaluate(model, y)
    if tag is None and (mx["max_bound_violation"] + mx["max_integrality_violation"] + mx["max_row_violation"]) > 0:
        noisy += 1
        check_accept(name + " (noise)", text, model, {"x": y, "objective": ev})
if noisy < 5:
    fail(f"only {noisy} noisy cases ran")
# determinism
a = call(["verify"], (LP + "\n---\n" + json.dumps(good)).encode()).stdout
b = call(["verify"], (LP + "\n---\n" + json.dumps(good)).encode()).stdout
if a != b or not a:
    fail("not deterministic")

print(f"{checks} checks; accepted {counts['accepted']} models ({counts['highs']} with HiGHS's optimum); faults refused: bound {counts['bound']}, row {counts['row']}, "
      f"integrality {counts['integrality']}, objective {counts['objective']}; skipped (fault not applicable): {skipped}")
if counts["accepted"] < (10 if QUICK else 60) or counts["row"] == 0 or counts["integrality"] == 0:
    fail("too few cases ran: the gate would pass for the wrong reason")
print("PASS" if bad == 0 else f"{bad} FAILED")
sys.exit(1 if bad else 0)
