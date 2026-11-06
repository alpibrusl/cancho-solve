#!/usr/bin/env python3
"""Gate 8 (docs/design.md 22.1): the MIR cuts with path aggregation and the RINS driver never change an answer, and they do what is claimed. Written before lib/mip/cmir.cho; it must fail on
a build without them (the effect table, the node counts and G3's `prof` reading do) and on a build whose cuts are wrong (G1).
G1 validity (with the defaults and with the cuts built before the search, `--experiment 256`; the number of cuts found and kept by the second is held exactly): generated tight and ample EV models, facility-location models, 60 random big-M models (`mixed`), 24 random mixed-integer models with general integers, equalities and negative
   coefficients (lpgen.random_mip) and knapsacks and set covers (lpgen): status and optimal value with the defaults equal HiGHS's to 1e-6 relative, and also those without MIR cuts and without
   the driver (`--experiment 96`) when that search finishes; the incumbent passes `solve verify`.
G2 effect: the root bound (`--node-limit 1`; with the cuts `--node-limit 301`, since they are added after the first 300 nodes, 22.1) of the tight EV models 6x8, 8x10, 10x12 and 12x12 rises to the optimum, exactly (table EFFECT below, re-measured on purpose), the bound without MIR
   cuts is the one of 19.8, and 6x8 and 8x10 are proved in fewer than 2,000 nodes (they take more than 10,000 and 300,000 without).
G3 pausing: on instances whose search takes more than 900 nodes the optimum with the driver and without it (`--experiment 32`) agree and verify (bit 128 adds the profile `stats.prof` to the report); on an instance that takes fewer than 300 nodes
   the node count is the same either way; the number of sub-MIPs run (`stats.prof[62]`) is positive on the first kind (run with the MIR cuts off, `--experiment 64`, because with them 6x8 is solved at the root) and zero on the second.
G4 RINS does not hurt: under node limits 299, 300, 301, 899, 900, 901, 2700 the incumbent is feasible, `bound` brackets HiGHS's optimum, and the incumbent is within half a percent of the one
   the same limit gives without the driver (it was "never worse" until design.md 22.6, which says why that stopped holding).
Needs scipy. Usage: SOLVE=build/solve python3 scripts/check_mir.py [--print]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpgen
from evgen import generate
from gen_models import sh, solve, highs, facility, mixed

FAILFAST = os.environ.get("FAILFAST") == "1"   # the mutant runner stops at the first failure
fails = []
checks = 0
skipped = []
OFF = ["--experiment", "96"]      # 32 no pausing and RINS, 64 no MIR cuts: the search of 19.8


class _Fails(list):
    def append(self, x):
        super().append(x)
        if FAILFAST:
            print("FAIL", x)
            sys.exit(1)


fails = _Fails()


def agree(a, b):
    return a is not None and b is not None and abs(a - b) <= 1e-6 * (1 + abs(b))


FOUND = KEPT = 0     # cuts found and kept by the eager rounds on the validity instances (held exactly below)


def validity(name, text):
    """The defaults and the eager rounds (experiment bit 256: the cuts are built before the search, so that models of fewer than 300 nodes use them) against HiGHS."""
    global checks, FOUND, KEPT
    checks += 1
    new, _ = solve(text)
    eager, _ = solve(text, ["--experiment", "384"])    # 256 eager + 128 profile
    if new["status"] in ("feasible", "unknown") or eager["status"] in ("feasible", "unknown"):
        skipped.append(name)
        return new
    FOUND += eager["stats"]["prof"][67]
    KEPT += eager["stats"]["prof"][68]
    hs, hv = highs(text)
    ok = new["status"] == hs and eager["status"] == hs
    if ok and hs == "optimal":
        ok = agree(new["objective"], hv) and agree(eager["objective"], hv)
        ok = ok and sh(["verify"], text + "---\n" + json.dumps(new)).returncode == 0 and sh(["verify"], text + "---\n" + json.dumps(eager)).returncode == 0
        old, _ = solve(text, OFF)
        if old["status"] == "optimal":
            ok = ok and agree(old["objective"], hv)
    if not ok:
        fails.append(f"{name}: defaults {new.get('status')} {new.get('objective')}, eager {eager.get('status')} {eager.get('objective')}, HiGHS {hs} {hv}")
    return new


for setting in ("ample", "tight"):
    for V, T in ((3, 6), (4, 6), (5, 7), (6, 8), (8, 10)):
        for seed in (1, 2, 3):
            validity(f"ev {setting} {V}x{T} seed {seed}", generate(V, T, setting, seed))
for F, C in ((3, 4), (4, 5), (5, 6)):
    for seed in range(1, 6):
        validity(f"facility {F}x{C} seed {seed}", facility(F, C, seed, seed % 2 == 0))
for seed in range(1, 61):
    validity(f"mixed seed {seed}", mixed(seed))
for seed in range(1, 25):
    validity(f"random_mip seed {seed}", lpgen.random_mip(seed, 12 + seed % 7, 14 + seed % 5, 0.4, 0.6 if seed % 2 else 1.0, infeasible=seed % 11 == 0))
for seed in range(1, 9):
    validity(f"knapsack seed {seed}", lpgen.knapsack(seed, 30 + seed * 5))
    validity(f"set cover seed {seed}", lpgen.set_cover(seed, 20 + seed * 3, 30 + seed * 4, 0.1))
if len(skipped) > 6:
    fails.append(f"{len(skipped)} instances ran into the node limit: {skipped}")
EXPECTED_FOUND, EXPECTED_KEPT = 25859, 1333     # measured once (python3 scripts/check_mir.py --print; re-measured on purpose for the warm cut rounds of design.md 22.3, was 13853 and 2174; 7061 and 1582 before the cold retries): cuts found and kept by the eager rounds on the validity instances, held exactly
if "--print" not in sys.argv and (FOUND, KEPT) != (EXPECTED_FOUND, EXPECTED_KEPT):
    fails.append(f"the eager rounds found {FOUND} cuts and kept {KEPT} on the validity instances (exactly {EXPECTED_FOUND} and {EXPECTED_KEPT} expected)")
if FOUND == 0:
    fails.append("no instance got a MIR cut: the gate cannot fail")

# G2
EFFECT = {"6x8": (35.58, 35.76), "8x10": (42.95, 43.30), "10x12": (72.22, 72.52), "12x12": (69.12, 69.16)}   # root bound without MIR cuts, with them (== optimum)
roots = {}
for key, (before, after) in EFFECT.items():
    V, T = map(int, key.split("x"))
    text = generate(V, T, "tight", 7)
    b_off, _ = solve(text, ["--node-limit", "1"] + OFF)
    b_on, _ = solve(text, ["--node-limit", "301"])   # the first 300 nodes run without the cuts, the 301st is the root of the search with them
    roots[key] = (b_off.get("bound"), b_on.get("bound"))
    checks += 1
    if not (agree(b_off.get("bound"), before) and agree(b_on.get("bound"), after)):
        fails.append(f"root bound {key}: without {b_off.get('bound')} (expected {before}), with {b_on.get('bound')} (expected {after})")
for key in ("6x8", "8x10"):
    V, T = map(int, key.split("x"))
    r, _ = solve(generate(V, T, "tight", 7))
    checks += 1
    if r["status"] != "optimal" or r["stats"]["nodes"] >= 2000:
        fails.append(f"tight {key}: {r['status']} in {r.get('stats', {}).get('nodes')} nodes (optimal in fewer than 2,000 expected)")

# G3 and G4
def prof(r, k):
    return r["stats"]["prof"][k]      # present only with experiment bit 128; a KeyError here is a gate that cannot see what it judges


text = generate(6, 8, "tight", 7)                # 11,557 nodes without the cuts
short = generate(3, 6, "tight", 1)               # finishes in fewer than 300 nodes
big = [generate(8, 10, "tight", 7), generate(12, 12, "tight", 7)]
ra, _ = solve(short, ["--experiment", "128"])
rb, _ = solve(short, ["--experiment", "160"])
checks += 1
if ra["stats"]["nodes"] != rb["stats"]["nodes"] or ra["stats"]["nodes"] >= 300 or prof(ra, 62) != 0:
    fails.append(f"short instance: nodes {ra['stats']['nodes']} vs {rb['stats']['nodes']}, sub-MIPs {prof(ra, 62)}")
LIM = (299, 300, 301, 899, 900, 901, 2700)
rins_worse = []
for t_i, t in enumerate(big + [text]):
    hs, hv = highs(t)
    for lim in LIM:
        a, _ = solve(t, ["--node-limit", str(lim), "--experiment", "64"])
        b, _ = solve(t, ["--node-limit", str(lim), "--experiment", "96"])
        c_, _ = solve(t, ["--node-limit", str(lim)])
        checks += 1
        for tag, r in (("driver", a), ("plain", b), ("cuts and driver", c_)):
            if r["status"] in ("feasible", "optimal"):
                if r["objective"] < hv - 1e-6 * (1 + abs(hv)) or sh(["verify"], t + "---\n" + json.dumps(r)).returncode != 0:
                    fails.append(f"instance {t_i} limit {lim} {tag}: incumbent {r['objective']} below the optimum {hv} or not verified")
                if r.get("bound") is not None and r["bound"] > hv + 1e-6 * (1 + abs(hv)):
                    fails.append(f"instance {t_i} limit {lim} {tag}: bound {r['bound']} above the optimum {hv}")
        if a["status"] in ("feasible", "optimal") and b["status"] in ("feasible", "optimal"):
            # design.md 22.6: "never worse" was an empirical claim and stopped holding when the plain search got better (restore from the previous node's state): RINS is worse on 4 of these 21
            # pairs, all on instance 1, by 0.23 percent at most, better on 1 and equal on 16; it is held to within half a percent, and to being worse on at most 5 of the 21 pairs
            rins_worse.append((a["objective"] - b["objective"]) / abs(b["objective"]))
            if a["objective"] > b["objective"] * (1 + 0.005) + 1e-9:
                fails.append(f"instance {t_i} limit {lim}: the driver's incumbent {a['objective']} is more than half a percent worse than the plain search's {b['objective']}")
    full_a, _ = solve(t, ["--experiment", "192"])
    full_b, _ = solve(t, ["--experiment", "96"])
    checks += 1
    if full_a["status"] == "optimal" and full_b["status"] == "optimal" and not agree(full_a["objective"], full_b["objective"]):
        fails.append(f"instance {t_i}: optimum {full_a['objective']} with the driver, {full_b['objective']} without")
    if t_i == 2 and prof(full_a, 62) <= 0:
        fails.append("the driver ran no sub-MIP on the 6x8 model (11,557 nodes without it): the gate cannot fail")

if "--print" in sys.argv:
    print("EFFECT =", {k: tuple(round(v, 2) if v else v for v in roots[k]) for k in roots})
    print("EXPECTED_FOUND, EXPECTED_KEPT =", FOUND, KEPT)
for f in fails:
    print("FAIL", f)
checks += 1
if sum(1 for x in rins_worse if x > 1e-9) > 5:
    fails.append(f"the driver is worse than the plain search on {sum(1 for x in rins_worse if x > 1e-9)} of {len(rins_worse)} (instance, limit) pairs, at most 5 allowed")
print(f"MIR/RINS gate: {'passed' if not fails else 'FAILED'} ({checks} checks, {len(skipped)} skipped at the node limit, {len(fails)} failures)")
sys.exit(1 if fails else 0)
