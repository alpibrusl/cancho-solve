#!/usr/bin/env python3
"""Gate 12 (docs/design.md 22.12): the presolve of the MIP search (experiment bit 33554432) drops the rows and fixes the columns the rules of 22.12 say it must, and it never changes an answer.
Written before `lib/mip/mpre.cho`; it fails on a build without the bit (G1 counts nothing dropped) and on a presolve that drops a row it should not (G2: an answer moves).
G1 rules: one hand model per rule (redundant row, singleton row, fixed column, dual fixing of a real and of an integer column, rounding of an integer bound), with the rows dropped, the columns fixed
   and the bounds tightened read from `stats.prof` (slots 55, 56, 57 = prof[45], prof[46], prof[47]; bit 128), and the optimum held against the run without the bit and the value written here.
G2 agreement: on generated tight EV, facility-location and `mixed` models the status and the optimum with the bit equal those without it to 1e-7 relative, and HiGHS's, and the answer is verified.
   One model is held as a known regression (KNOWN_UNPROVEN): tight 10 x 12 seed 1 is proved without the presolve (301 nodes, the MIR rounds close its root gap) and not with it (80.79 against
   80.85 after 200,000 nodes; the original model without its MIR cuts has the same plateau, 22.12.1). The gate fails when that stops being true either way.
G3 infeasible: models that the activity bounds prove infeasible give `infeasible` with the bit, as without it.
G5 strength: the rounding of an integer column's bound from a row (two hand models, answers that are wrong without it) and the rounds, cuts found and kept of the eager cut rounds on two models (they use the
   presolve's bounds: a build whose rounds ignore them gives other counts).
G4 effect: 24 x 16 seed 7 drops at least 500 rows, and the iterations of the whole search are at most 80 percent of those without the bit, with the same optimum (claims 1 of 22.12; seconds are in the design, not here:
   a timing is not a gate).
Needs scipy for the oracle. Usage: SOLVE=build/solve python3 scripts/check_mpre.py [--print]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate
from gen_models import solve, facility, mixed, highs

BIT = 33554432
fails = []
checks = 0
PRINT = "--print" in sys.argv


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run(text, bit, extra=(), nodes=200000, more=0):
    d, _ = solve(text, ["--experiment", str(128 + more + (BIT if bit else 0)), "--node-limit", str(nodes)] + list(extra))
    return d


def close(a, b):
    return a is not None and b is not None and abs(a - b) <= 1e-7 * (1 + abs(b))


def guarded(text):
    """A model with only real columns takes the LP path, which has its own presolve; one more integer column, in a row nothing else can drop, sends it to the MIP search: b and u, cost 1 each,
    g: b + u >= 0.5 (not redundant, not a singleton, both columns held by a row that wants them up). It adds 0.5 to the optimum and nothing to the counts."""
    return "var b : bool;\nvar u : real 0..10;\n" + text.replace("minimize t: ", "minimize t: b + u + ") + "    g: b + u >= 0.5;\n"


# (name, model, optimum, rows dropped, columns fixed, bounds tightened): counts derived by hand from the rules of 22.12 before the code, and held exactly (`--print` shows what a build gives)
HAND = [
    ("redundant row", guarded("var x : real 0..10;\nvar y : real 0..10;\nminimize t: x + y;\nsubject to\n    a: x + y >= 3;\n    b: x + y <= 100;\n"), 3.5, 1, 0, 0),
    ("singleton row", guarded("var x : real 0..10;\nvar y : real 0..10;\nminimize t: x + 2*y;\nsubject to\n    a: x + y >= 5;\n    s: 2*x >= 4;\n"), 5.5, 1, 0, 1),
    ("fixed column", guarded("var x : real 0..10;\nvar y : real 0..10;\nvar f : real 3..3;\nminimize t: x + y + f;\nsubject to\n    a: x + y >= 2;\n    r: x + f <= 5;\n"), 5.5, 1, 0, 1),
    ("dual fixing, real", guarded("var x : real 0..10;\nvar y : real 0..10;\nvar w : real 0..10;\nminimize t: x + y + w;\nsubject to\n    a: x + y >= 3;\n    c: y + w <= 12;\n"), 3.5, 1, 1, 0),
    ("dual fixing, integer", "var x : real 0..10;\nvar y : real 0..10;\nvar k : int 0..5;\nminimize t: x + y + 2*k;\nsubject to\n    a: x + y >= 3;\n    c: y + k <= 12;\n", 3.0, 1, 1, 0),
    ("dual fixing, maximize", "var b : bool;\nvar u : real 0..10;\nvar x : real 0..10;\nvar y : real 0..10;\nvar w : real 0..10;\nmaximize t: -b - u - x - y - w;\nsubject to\n    g: b + u >= 0.5;\n    a: x + y >= 3;\n    c: y + w <= 12;\n", -3.5, 1, 1, 0),
    ("integer bound rounding", "var x : real 0..10;\nvar k : int 0..5;\nminimize t: x + k;\nsubject to\n    s: 3*k >= 4;\n    c: x + k >= 3;\n", 3.0, 1, 0, 1),
]
INFEASIBLE = [
    ("activity", guarded("var x : real 0..10;\nvar y : real 0..10;\nminimize t: x + y;\nsubject to\n    a: x + y >= 30;\n")),
    ("singleton crossing", guarded("var x : real 0..10;\nminimize t: x;\nsubject to\n    a: x >= 6;\n    b: x <= 4;\n")),
    ("rounding crosses in one row", guarded("var k : int 0..5;\nminimize t: k;\nsubject to\n    a: 3*k == 4;\n")),
    ("empty row after fixing", guarded("var f : real 3..3;\nminimize t: f;\nsubject to\n    r: f >= 5;\n")),
    ("integer rounding", "var k : int 0..5;\nminimize t: k;\nsubject to\n    a: 3*k >= 4;\n    b: 3*k <= 5;\n"),
]

for name, text, opt, rows, cols, bnds in HAND:
    d1 = run(text, True)
    d0 = run(text, False)
    p = (d1.get("stats", {}).get("prof") or [0] * 80) if isinstance(d1, dict) else [0] * 80
    got = (p[45], p[46], p[47])
    if PRINT:
        print("    (%r, ..., %r, %d, %d, %d)," % (name, d1.get("objective"), got[0], got[1], got[2]))
    need(d1.get("status") == "optimal" and close(d1.get("objective"), opt), "%s: with the presolve %s %s, optimum %s expected" % (name, d1.get("status"), d1.get("objective"), opt))
    need(close(d0.get("objective"), opt), "%s: without the presolve %s, optimum %s expected" % (name, d0.get("objective"), opt))
    need(got == (rows, cols, bnds), "%s: (rows dropped, columns fixed by the rules, bounds tightened by a singleton row) = %s, %s expected" % (name, got, (rows, cols, bnds)))

for name, text in INFEASIBLE:
    d1 = run(text, True)
    d0 = run(text, False)
    need(d0.get("status") == "infeasible", "%s: without the presolve %s, infeasible expected (the model is wrong)" % (name, d0.get("status")))
    need(d1.get("status") == "infeasible", "%s: with the presolve %s, infeasible expected" % (name, d1.get("status")))

# G5 rounding (mutants 13 and 14 of 22.12.1): the bound a row gives an integer column is rounded inward, and the dual fixing then fixes the column there. The objective is not whole (a real column
# with a half in its cost), so nothing else rounds it: without the rounding the column is fixed at 4/3 or 14/3 and the answer is wrong.
ROUND = [
    ("lower bound rounded up", "var k : int 0..5;\nvar x : real 0..10;\nminimize t: k + 0.5*x;\nsubject to\n    s: 3*k >= 4;\n    c: x >= 0.2;\n", 2.1),
    ("upper bound rounded down", "var k : int 0..5;\nvar x : real 0..10;\nmaximize t: k + 0.5*x;\nsubject to\n    s: 3*k <= 14;\n    c: x <= 0.2;\n", 4.1),
]
for name, text, opt in ROUND:
    d1 = run(text, True, nodes=1)
    need(d1.get("status") == "optimal" and close(d1.get("objective"), opt), "%s: with the presolve %s %s in one node, optimal %s expected" % (name, d1.get("status"), d1.get("objective"), opt))
    need(d1.get("verified", True) is True, "%s: the answer is not verified" % name)

# the cut rounds use the presolve's bounds: the rounds, the cuts found and kept (eager rounds, bit 256) of two models are held exactly (`--print` re-measures them)
ROUNDS = {
    "tight 10x12 seed 2": (54, 569, 110),
    "tight 12x12 seed 4": (213, 906, 99),
    "tight 24x16 seed 7": (152, 1806, 137),
}
for name, (v, t, s) in (("tight 10x12 seed 2", (10, 12, 2)), ("tight 12x12 seed 4", (12, 12, 4)), ("tight 24x16 seed 7", (24, 16, 7))):
    d = run(generate(v, t, "tight", s), True, nodes=1, more=256)
    pr = d.get("stats", {}).get("prof") or [0] * 80
    got = (pr[66], pr[67], pr[68])
    if PRINT:
        print("    %r: %r," % (name, got))
    need(ROUNDS[name] == got, "%s: (rounds, cuts found, cuts kept) = %s with the presolve, %s expected" % (name, got, ROUNDS[name]))

models = []
for v, t in [(6, 8), (8, 10), (10, 12)]:
    for s in range(1, 5):
        models.append(("tight %dx%d seed %d" % (v, t, s), generate(v, t, "tight", s)))
for s in range(1, 21):
    models.append(("facility 6/8 seed %d" % s, facility(6, 8, s, varied=(s % 2 == 0))))
for s in range(60):
    models.append(("mixed seed %d" % s, mixed(s)))

KNOWN_UNPROVEN = {"tight 10x12 seed 1"}
dropped_total = 0
for name, text in models:
    d1 = run(text, True)
    d0 = run(text, False)
    st = d1.get("status")
    if name in KNOWN_UNPROVEN:
        need(d0.get("status") == "optimal" and st == "feasible" and close(d1.get("objective"), d0.get("objective")),
             "%s: expected proved without the presolve and unproven with it at the same incumbent, got %s %s and %s %s" % (name, d0.get("status"), d0.get("objective"), st, d1.get("objective")))
        continue
    need(st == d0.get("status"), "%s: status %s with the presolve, %s without" % (name, st, d0.get("status")))
    if st == "optimal":
        need(close(d1.get("objective"), d0.get("objective")), "%s: optimum %s with the presolve, %s without" % (name, d1.get("objective"), d0.get("objective")))
        hs, hv = highs(text)
        need(hs == "optimal" and close(d1.get("objective"), hv), "%s: optimum %s, HiGHS %s %s" % (name, d1.get("objective"), hs, hv))
        need(d1.get("verified", True) is True, "%s: the answer is not verified" % name)
    p = d1.get("stats", {}).get("prof") or [0] * 80
    dropped_total += p[45]
need(dropped_total > 0, "no row was dropped on any generated model")

big = generate(24, 16, "tight", 7)
d1 = run(big, True)
d0 = run(big, False)
p = d1.get("stats", {}).get("prof") or [0] * 80
if PRINT:
    print("24x16 seed 7: dropped", p[45], "iterations", d1["stats"]["iterations"], "against", d0["stats"]["iterations"])
need(d1.get("status") == "optimal" and close(d1.get("objective"), d0.get("objective")), "24x16 seed 7: optimum %s with the presolve, %s without" % (d1.get("objective"), d0.get("objective")))
need(p[45] >= 500, "24x16 seed 7: %d rows dropped, at least 500 expected (518 for the LP presolve, 518 for CBC)" % p[45])
need(d1["stats"]["iterations"] * 5 <= d0["stats"]["iterations"] * 4, "24x16 seed 7: %d iterations against %d (at most 80 percent expected)" % (d1["stats"]["iterations"], d0["stats"]["iterations"]))

if fails:
    print("presolve gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("presolve gate: passed (%d checks, %d rows dropped over the generated models, 0 failures)" % (checks, dropped_total))
