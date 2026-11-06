#!/usr/bin/env python3
"""Gate 11 (docs/design.md 22.9): the sub-MIPs of the driver run cut rounds of their own, and that finds plans the sub-MIPs of 22.8 did not. Written before the code; it fails on a build without it.
G1 effect (30,000 nodes, defaults against `--experiment 4194304`, the sub-MIPs of 22.8): the page's tight 24 x 16 (seed 7) is proved in 3,000 nodes (24,600 off) and seed 9 in 3,000 (not proved in 30,000 off,
   192.21 against the optimum 192.11); seeds 4, 6 and 8 end with the incumbents 173.30, 195.89 and 194.61 against 173.54, 196.08 and 194.72: each held exactly and each strictly better.
G2 the rounds run: `stats.prof[77]` (the rounds of all the sub-MIPs, 289 on the page's model) is positive with the defaults and zero with bit 4194304.
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


def run(t, bits, lim=30000):
    r, _ = solve(t, ["--experiment", str(128 + bits), "--node-limit", str(lim)])
    return r


# (name, seed, expected on: (status, objective, nodes, rounds), expected off: (status, objective, nodes))
CASES = [("page 24x16 (seed 7)", 7, ("optimal", 191.45, 3000, 289), ("optimal", 191.45, 24600)),
         ("24x16 seed 9", 9, ("optimal", 192.11, 3000, 268), ("feasible", 192.21, 30000)),
         ("24x16 seed 4", 4, ("feasible", 173.3, 30000, 437), ("feasible", 173.54, 30000)),
         ("24x16 seed 6", 6, ("feasible", 195.89, 30000, 479), ("feasible", 196.08, 30000)),
         ("24x16 seed 8", 8, ("feasible", 194.61, 30000, 466), ("feasible", 194.72, 30000))]
for name, seed, on, off in CASES:
    t = generate(24, 16, "tight", seed)
    a, b = run(t, 0), run(t, OFF)
    ga = (a["status"], round(a["objective"], 3), a["stats"]["nodes"], a["stats"]["prof"][77])
    gb = (b["status"], round(b["objective"], 3), b["stats"]["nodes"])
    need(ga == on, "%s: with the rounds %s, exactly %s expected" % (name, ga, on))
    need(gb == off, "%s: without %s, exactly %s expected" % (name, gb, off))
    need(b["stats"]["prof"][77] == 0, "%s: bit 4194304 still runs %d rounds in the sub-MIPs" % (name, b["stats"]["prof"][77]))
    need(a["objective"] < b["objective"] - 1e-9 or (a["status"] == "optimal" and b["status"] == "optimal" and a["stats"]["nodes"] < b["stats"]["nodes"]),
         "%s: neither a better incumbent (%s against %s) nor a shorter proof (%s nodes against %s)" % (name, a["objective"], b["objective"], a["stats"]["nodes"], b["stats"]["nodes"]))
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
