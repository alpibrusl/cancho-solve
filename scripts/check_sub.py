#!/usr/bin/env python3
"""Gate 11 (docs/design.md 22.9): the sub-MIPs of the driver run cut rounds of their own, and that finds plans the sub-MIPs of 22.8 did not. Written before the code; it fails on a build without it.
G1 effect (30,000 nodes, defaults against `--experiment 4194304`, the sub-MIPs of 22.8; numbers with the presolve as the default, 22.12.3): the page's tight 24 x 16 (seed 7) is proved in 3,000 nodes (not proved
   in 30,000 off, 191.48), seed 9 in 3,000 (192.27 off), seeds 6 and 8 in 8,400 (196.02 and 195.06 off); seed 4 ends at 173.30 on both (before the presolve: 173.30 against 173.54, strictly better; corrected here).
G2 the rounds run: `stats.prof[77]` (the rounds of all the sub-MIPs, 286 on the page's model) is positive with the defaults and zero with bit 4194304.
G3 nothing moves where the driver does not run: an instance that finishes in fewer than 300 nodes gives the same nodes, iterations and objective with and without the bit.
G4 answers: the optimum of each proved model is HiGHS's (computed here).
Needs scipy. Usage: SOLVE=build/solve python3 scripts/check_sub.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate
from gen_models import solve, highs

OFF = 4194304
fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


NORESTART = 134217728    # no restarts of the root rounds from perturbed costs (design.md 22.15): the pins below are of the sub-MIP rounds as measured before them; check_restart.py holds the default


def run(t, bits, lim=30000):
    r, _ = solve(t, ["--experiment", str(128 + NORESTART + bits), "--node-limit", str(lim)])
    return r


# (name, seed, expected on: (status, objective, nodes, rounds), expected off: (status, objective, nodes), strictly better required)
# Measured with the presolve as the default (design.md 22.12.3); the numbers before it are in 22.9. Seed 4 is a tie now (173.30 on both), held as no worse.
CASES = [("page 24x16 (seed 7)", 7, ("optimal", 191.45, 3000, 286), ("feasible", 191.48, 30000), True),
         ("24x16 seed 9", 9, ("optimal", 192.11, 3000, 288), ("feasible", 192.27, 30000), True),
         ("24x16 seed 4", 4, ("feasible", 173.3, 30000, 472), ("feasible", 173.3, 30000), False),
         ("24x16 seed 6", 6, ("optimal", 195.8, 8400, 376), ("feasible", 196.02, 30000), True),
         ("24x16 seed 8", 8, ("optimal", 194.58, 8400, 373), ("feasible", 195.06, 30000), True)]
# the iterations of the runs with the rounds, held exactly (a search that forgets the iterations it had done when it resumes after a pause reports fewer: mutants_cmir.py 54)
ITERS = {7: 37271, 9: 40569, 4: 211085, 6: 69289, 8: 75921}
for name, seed, on, off, strict in CASES:
    t = generate(24, 16, "tight", seed)
    a, b = run(t, 0), run(t, OFF)
    ga = (a["status"], round(a["objective"], 3), a["stats"]["nodes"], a["stats"]["prof"][77])
    gb = (b["status"], round(b["objective"], 3), b["stats"]["nodes"])
    need(ga == on, "%s: with the rounds %s, exactly %s expected" % (name, ga, on))
    need(a["stats"]["iterations"] == ITERS[seed], "%s: %d iterations, exactly %d expected" % (name, a["stats"]["iterations"], ITERS[seed]))
    need(gb == off, "%s: without %s, exactly %s expected" % (name, gb, off))
    need(b["stats"]["prof"][77] == 0, "%s: bit 4194304 still runs %d rounds in the sub-MIPs" % (name, b["stats"]["prof"][77]))
    better = a["objective"] < b["objective"] - 1e-9 or (a["status"] == "optimal" and b["status"] == "optimal" and a["stats"]["nodes"] < b["stats"]["nodes"]) or (a["status"] == "optimal" and b["status"] != "optimal")
    if strict:
        need(better, "%s: neither a better incumbent (%s against %s) nor a shorter proof (%s nodes against %s)" % (name, a["objective"], b["objective"], a["stats"]["nodes"], b["stats"]["nodes"]))
    else:
        need(a["objective"] <= b["objective"] + 1e-9, "%s: the rounds give a worse incumbent (%s against %s)" % (name, a["objective"], b["objective"]))
    if a["status"] == "optimal":
        hs, hv = highs(t)
        need(abs(a["objective"] - hv) <= 1e-6 * (1 + abs(hv)), "%s: optimum %s, HiGHS %s" % (name, a["objective"], hv))
short = generate(10, 12, "tight", 1)
a, b = run(short, 0, 250), run(short, OFF, 250)
need(a["stats"]["nodes"] == b["stats"]["nodes"] and a["stats"]["iterations"] == b["stats"]["iterations"] and a["stats"]["prof"][77] == 0,
     "an instance of fewer than 300 nodes differs: nodes %s / %s, iterations %s / %s, rounds %s" % (a["stats"]["nodes"], b["stats"]["nodes"], a["stats"]["iterations"], b["stats"]["iterations"], a["stats"]["prof"][77]))

if fails:
    print("sub-MIP gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("sub-MIP gate: passed (%d checks, 0 failures)" % checks)
