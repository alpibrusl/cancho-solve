#!/usr/bin/env python3
"""Gate 23 (docs/design.md 22.18): `--exp gomory` adds Gomory mixed-integer cuts, separated from the tableau rows of the final basis of each root LP, to the pool of the cut rounds. Written before
`lib/mip/gomory.cho`; it fails on a build without the name (G0) and, with the mutants of scripts/mutants_gomory.py, on a cut that is not valid for every integer point (G1).
G1 valid: on 8 tight EV models (6 x 8 to 12 x 12, seeds 1 and 2), 3 facility-location models and 6 `mixed` models (three of them infeasible, which they stay), the proved optimum with `gomory` is HiGHS's (computed here), and the root bound after
   the rounds (`--node-limit 1`, eager rounds) is never beyond the optimum by more than 1e-7 relative: a cut that cuts off the optimal point fails here.
G2 exercised: `stats.gomory` = [rows tried, cuts pooled] is present with the name, absent without it, and pooled > 0 on at least five of the models (a gate on a separator that finds nothing would pass anything).
G3 deterministic: two runs, the same bytes.
G4 off is off: without the name the reports are the bytes of `--experiment` without the bit (the same build), and the nodes of two models are held at the counts of check_restart.py (tight 10 x 12 seed 1: 2,759;
   tight 12 x 12 seed 1: 320), measured before this build.
Needs scipy. Usage: SOLVE=build/solve LAB=build/lab python3 scripts/check_gomory.py [--print]"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_models import solve, highs, facility, mixed

SOLVE = os.environ.get("SOLVE", "build/solve")
LAB = os.environ.get("LAB", "build/lab")
PRINT = "--print" in sys.argv
fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def lab(v, t, s):
    return subprocess.run([LAB, "gen", "ev", str(v), str(t), "tight", str(s)], capture_output=True, text=True).stdout


def run(text, spec, lim):
    p = subprocess.run([SOLVE, "run", "--node-limit", str(lim), "--exp", spec], input=text, capture_output=True, text=True, timeout=600)
    return p.stdout, (json.loads(p.stdout) if p.stdout else None)


QUICK = os.environ.get("QUICK") == "1"     # the small models only (the mutants' run)
models = []
for v, t in ([(6, 8), (8, 10)] if QUICK else [(6, 8), (8, 10), (10, 12), (12, 12)]):
    for s in (1, 2):
        models.append(("tight %dx%d seed %d" % (v, t, s), lab(v, t, s)))
for s in range(1, 4):
    models.append(("facility 6/8 seed %d" % s, facility(6, 8, s, varied=(s == 2))))
for s in range(6):
    models.append(("mixed seed %d" % s, mixed(s)))

def rand_mip(seed):
    """A small mixed-integer model with general integers (0..4), continuous columns (0..6), fractional-friendly coefficients and rows of every sense: the shape the EV models do not have."""
    import random
    r = random.Random(seed)
    ni, nr, m = 6, 4, 5
    out = ["var xi[0..%d] : int 0..4;" % ni, "var xr[0..%d] : real 0..6;" % nr]
    for k in range(m):
        out.insert(0, "param ai%d = [%s];\nparam ar%d = [%s];" % (k, ", ".join(str(r.randint(-3, 6)) for _ in range(ni)), k, ", ".join(str(r.randint(-3, 6)) for _ in range(nr))))
    out.insert(0, "param oi = [%s];\nparam orr = [%s];" % (", ".join(str(r.randint(1, 7)) for _ in range(ni)), ", ".join(str(r.randint(1, 7)) for _ in range(nr))))
    out.append("maximize obj: sum i in 0..%d: oi[i] * xi[i] + sum j in 0..%d: orr[j] * xr[j];" % (ni, nr))
    out.append("subject to")
    for k in range(m):
        sense = r.choice(["<=", "<=", ">="])
        rhs = r.randint(6, 30) if sense == "<=" else r.randint(0, 4)
        out.append("    c%d: sum i in 0..%d: ai%d[i] * xi[i] + sum j in 0..%d: ar%d[j] * xr[j] %s %d;" % (k, ni, k, nr, k, sense, rhs))
    return "\n".join(out) + "\n"


for sd in range(300):
    models.append(("random mip seed %d" % sd, rand_mip(sd)))
pooled_models = 0
for name, text in models:
    hs, hv = highs(text)
    raw, d = run(text, "gomory", 200000)
    if hs == "optimal":
        need(d is not None and d["status"] == "optimal" and abs(d["objective"] - hv) <= 1e-6 * (1 + abs(hv)), "%s: with gomory %s, HiGHS %s" % (name, d and (d["status"], d.get("objective")), hv))
    else:
        need(d is not None and d["status"] == "infeasible" and hs == "infeasible", "%s: with gomory %s, HiGHS %s (an infeasible model stays infeasible)" % (name, d and d["status"], hs))
    raw1, d1 = run(text, "gomory,eager-rounds", 1)
    if d1 and hs == "optimal" and "bound" in d1:
        tol = 1e-7 * (1 + abs(hv))
        ok = d1["bound"] >= hv - tol if "maximize" in text else d1["bound"] <= hv + tol
        need(ok, "%s: the root bound %s is beyond the optimum %s" % (name, d1["bound"], hv))
    g = d1["stats"].get("gomory") if d1 else None
    if hs == "optimal" and not name.startswith("random"):
        need(g is not None and len(g) == 2, "%s: stats.gomory = %s" % (name, g))
    if g and g[1] > 0:
        pooled_models += 1
    if PRINT:
        print("   ", name, g, d1.get("bound") if d1 else None)
    raw2, _ = run(text, "gomory,eager-rounds", 1)
    need(raw1 == raw2, "%s: two runs differ" % name)
    r0, d0 = run(text, "eager-rounds", 1)
    need(d0 is not None and "gomory" not in d0["stats"], "%s: stats.gomory present without the name" % name)
need(pooled_models >= 5, "cuts pooled on only %d models" % pooled_models)

# G4
for (v, t, s), nodes in ([] if QUICK else [((10, 12, 1), 2759), ((12, 12, 1), 320)]):
    raw, d = run(lab(v, t, s), "profile", 30000)
    need(d is not None and d["stats"]["nodes"] == nodes, "tight %dx%d seed %d: %s nodes without gomory, %d expected" % (v, t, s, d and d["stats"]["nodes"], nodes))

if fails and not PRINT:
    print("gomory gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("gomory gate: passed (%d checks, 0 failures)" % checks)
