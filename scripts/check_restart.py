#!/usr/bin/env python3
"""Gate 12 (docs/design.md 22.15): the root's cut rounds are run again, twice by default, from the optimum of costs perturbed by at most 1e-6 relative, on the same model (the cuts of every run
stay). Written before the default was changed; it fails on a build without the restarts (G1, G2) and on a build whose bound is taken from a perturbed LP (G3).
G1 effect (30,000 nodes): tight 10 x 12 seed 1, which no run without the restarts proved (80.79 against 80.85, 22.12.2), is proved with the default; the nodes of seven models with and without
   (experiment bit 134217728, `v` = 1 is no restart) are held exactly, and every proved optimum is HiGHS's (computed here).
G2 the bit: `v` = 3 is the default's two restarts (same bytes as no bit), `v` = 1 gives the rounds of 22.3 alone, with fewer rounds than the default (`prof[66]`) on models that need rounds.
G3 sound: with the rounds run first (bit 256) the root bound is never above the optimum (HiGHS's) by more than 1e-7 relative, on generated tight, facility and mixed models, so a perturbed LP never
   gives the bound; and two runs give the same bytes.
Needs scipy. Usage: SOLVE=build/solve python3 scripts/check_restart.py [--print]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate
from gen_models import solve, highs, facility, mixed

PRINT = "--print" in sys.argv
NONE = 134217728 * 1
TWO = 134217728 * 3
fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run(t, bits=0, lim=30000):
    r, _ = solve(t, ["--experiment", str(bits), "--node-limit", str(lim)])
    return r


# (name, model, (status, nodes) without the restarts, (status, nodes) with the default) measured once with --print and held exactly
CASES = [("tight 10x12 seed 1", (10, 12, 1)), ("tight 12x12 seed 1", (12, 12, 1)), ("tight 24x16 seed 4", (24, 16, 4)), ("tight 24x16 seed 6", (24, 16, 6)),
         ("tight 24x16 seed 7", (24, 16, 7)), ("tight 24x16 seed 8", (24, 16, 8)), ("tight 12x12 seed 3", (12, 12, 3))]
EXPECTED = {
    "tight 10x12 seed 1": (("feasible", 30000), ("optimal", 2759)),
    "tight 12x12 seed 1": (("optimal", 3883), ("optimal", 320)),
    "tight 24x16 seed 4": (("feasible", 30000), ("optimal", 600)),
    "tight 24x16 seed 6": (("optimal", 8400), ("optimal", 3000)),
    "tight 24x16 seed 7": (("optimal", 3000), ("optimal", 600)),
    "tight 24x16 seed 8": (("optimal", 8400), ("optimal", 1200)),
    "tight 12x12 seed 3": (("optimal", 600), ("optimal", 1571)),      # worse with the restarts: held as measured (22.15)
}
for name, (v, t, s) in CASES:
    text = generate(v, t, "tight", s)
    a, b = run(text, NONE), run(text, 0)
    got = ((a["status"], a["stats"]["nodes"]), (b["status"], b["stats"]["nodes"]))
    if PRINT:
        print("    %r: %r," % (name, got))
    need(EXPECTED.get(name) == got, "%s: (without, with) = %s, exactly %s expected" % (name, got, EXPECTED.get(name)))
    if b["status"] == "optimal":
        hs, hv = highs(text)
        need(hs == "optimal" and abs(b["objective"] - hv) <= 1e-6 * (1 + abs(hv)), "%s: optimum %s, HiGHS %s" % (name, b["objective"], hv))
    if name == "tight 10x12 seed 1":
        need(json.dumps(b, sort_keys=True) == json.dumps(run(text, TWO), sort_keys=True), "%s: bit 134217728 * 3 is not the default" % name)
text = generate(10, 12, "tight", 1)
need(run(text, NONE)["status"] != "optimal" and run(text, 0)["status"] == "optimal", "tight 10x12 seed 1: the restarts no longer make the difference")
for name, (v, t, s) in (("tight 10x12 seed 2", (10, 12, 2)), ("tight 12x12 seed 4", (12, 12, 4))):
    text = generate(v, t, "tight", s)
    pa = run(text, 384 + NONE, 1)["stats"]["prof"]
    pb = run(text, 384, 1)["stats"]["prof"]
    need(pb[66] > pa[66], "%s: %d rounds with the restarts, %d without: the restarts did not run" % (name, pb[66], pa[66]))

# G3
models = []
for s in range(1, 6):
    models.append(("tight 10x12 seed %d" % s, generate(10, 12, "tight", s)))
for s in range(1, 4):
    models.append(("facility 6/8 seed %d" % s, facility(6, 8, s, varied=(s == 2))))
for s in range(6):
    models.append(("mixed seed %d" % s, mixed(s)))
for name, text in models:
    d = run(text, 384, 1)
    hs, hv = highs(text)
    if hs == "optimal" and "bound" in d:
        tol = 1e-7 * (1 + abs(hv))
        ok = d["bound"] >= hv - tol if "maximize" in text else d["bound"] <= hv + tol
        need(ok, "%s: the root bound %s is on the wrong side of the optimum %s" % (name, d["bound"], hv))
    need(json.dumps(d, sort_keys=True) == json.dumps(run(text, 384, 1), sort_keys=True), "%s: two runs differ" % name)

if fails and not PRINT:
    print("restart gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("restart gate: passed (%d checks, 0 failures)" % checks)
