#!/usr/bin/env python3
"""Gate (docs/design.md 19.8): the implied cuts through variable upper bounds never change an answer, and they do what is claimed.
1. validity: on generated EV-depot instances (ample, tight and impossible chargers; several seeds), facility-location instances (the other big-M shape, with equal and with varied bounds) and 60
   random big-M models with every row shape the generator reads or refuses (`mixed`), the status and
   the optimal value with the cuts equal those without (`--experiment 104`: 8 no implied cuts, 32 no pausing and RINS, 64 no MIR cuts, 22.1) and HiGHS's (scipy milp on `solve expand`), to 1e-6 relative; the incumbent `solve verify` accepts.
2. effect: docs/examples/ev_depot_3.sol adds 6 cuts and takes exactly 1,498 nodes (15,206 without; 3,724 and 47,105 before the restore from the previous node's state, design.md 22.6), and its root bound rises from 26.58 to at least 27.2; a knapsack, which has no variable
   upper bound, gets 0 cuts; `--experiment 8` gives 0 cuts; and the number of cuts added on the generated instances and the sum of their root bounds are held exactly (a weaker or a stronger
   cut moves them).
Needs scipy. Usage: SOLVE=build/solve python3 scripts/check_cuts.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate

fails = []
skipped = []
checks = 0


from gen_models import sh, solve, highs, facility, mixed


def agree(a, b):
    return a is not None and b is not None and abs(a - b) <= 1e-6 * (1 + abs(b))


def validity(name, text):
    global checks
    checks += 1
    with_cuts, _ = solve(text)
    if with_cuts["status"] in ("feasible", "unknown"):   # the search ran into its node limit: nothing to compare
        skipped.append(name)
        return with_cuts
    without, _ = solve(text, ["--experiment", "104"])   # 104 = 8 (no implied cuts) + 32 (no pausing, no RINS) + 64 (no MIR cuts)
    hs, hv = highs(text)
    limited = without["status"] in ("feasible", "unknown")   # the plain search ran into its node limit (the cuts of 22.1 are what finish some of these): only HiGHS can judge
    ok = with_cuts["status"] == hs and (limited or without["status"] == hs)
    if ok and hs == "optimal":
        ok = agree(with_cuts["objective"], hv) and (limited or agree(without["objective"], hv))
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
        rb, _ = solve(mixed(seed), ["--node-limit", "1", "--experiment", "96"])
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
r, _ = solve(ev3, ["--experiment", "96"])   # 96 = 32 + 64: the search of 19.8 (no pausing, no RINS, no MIR cuts), whose count is held
checks += 1
if r["stats"]["cuts"] != 6 or r["stats"]["nodes"] != 1498 or abs(r["objective"] - 27.56) > 1e-6:
    fails.append(f"ev_depot_3: cuts {r['stats']['cuts']} (6), nodes {r['stats']['nodes']} (1498), objective {r.get('objective')}")
root, _ = solve(ev3, ["--node-limit", "1", "--experiment", "96"])
roff, _ = solve(ev3, ["--node-limit", "1", "--experiment", "104"])
checks += 1
if not (root.get("bound", 0) >= 27.2 and roff.get("bound", 0) <= 26.6):
    fails.append(f"root bound with cuts {root.get('bound')} (>= 27.2), without {roff.get('bound')} (<= 26.6)")
checks += 1
r8, _ = solve(ev3, ["--experiment", "104"])
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
