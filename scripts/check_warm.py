#!/usr/bin/env python3
"""Gate 9 (docs/design.md 22.3): the cut rounds that start from the previous basis give the value a solve from the slack basis gives, and they need far fewer iterations. Written before
`ws_load_warm`; it fails on a build whose warm load copies nothing, or copies the wrong thing (G1, mutants_warm.py), and on a build that falls back to cold solves (G2).
G1 agreement: on generated tight EV models, facility-location models and `mixed` models, the cut rounds built before the search (`--experiment 256`) with the self-check (`512`: every warm LP is
   also solved cold and the two values compared to 1e-7 relative) report no disagreement (`stats.prof[71]`) and a positive number of warm solves (`prof[70]`, one fewer than the rounds when the
   first LP ended the rounds, else all but the first).
G2 effect: on the tight EV models of 10 x 12 and 12 x 12 the iterations of the rounds with the warm start (`prof[69]`) are at most a fifth of those of the cold solves of the same rounds (`prof[72]`,
   measured in the same run), and the run with bit 1024 (every LP from the slack basis, the old behaviour) shows the old counts, so that the bit does what it says.
G3 exactness: the rounds, the cuts found and the iterations (warm and cold) of every instance are held exactly (EXPECTED; `--print` re-measures them).
Needs nothing but the built solve. Usage: SOLVE=build/solve python3 scripts/check_warm.py [--print]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate
from gen_models import solve, facility, mixed

fails = []
checks = 0


def prof(text, exp):
    d, _ = solve(text, ["--experiment", str(exp), "--node-limit", "1"])
    return d, (d.get("stats", {}).get("prof") if isinstance(d, dict) else None)


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


# (rounds, cuts found, iterations of the rounds, iterations of their cold solves) per instance, measured once with `python3 scripts/check_warm.py --print` and held exactly: the rounds are deterministic, and these
# are what notice a change in the weights, in what is counted or in what the LP reports (a mutant that only moves the iterations or the stopping of the rounds)
EXPECTED = {
    'tight 6x8': (23, 68, 333, 1343),
    'tight 8x10': (39, 218, 1058, 7415),
    'tight 10x12': (132, 687, 5088, 45939),
    'tight 12x12': (122, 803, 7341, 55084),
    'facility 6/8 seed 1': (1, 0, 21, 0),
    'facility 6/8 seed 2': (3, 9, 44, 22),
    'facility 6/8 seed 3': (8, 65, 71, 180),
    'mixed seed 0': (1, 0, 10, 0),
    'mixed seed 1': (1, 0, 10, 0),
    'mixed seed 2': (4, 4, 32, 30),
    'mixed seed 3': (4, 5, 29, 27),
    'mixed seed 4': (3, 1, 17, 8),
    'mixed seed 5': (6, 19, 41, 61),
}
PRINT = "--print" in sys.argv
models = []
for v, t in [(6, 8), (8, 10), (10, 12), (12, 12)]:
    models.append(("tight %dx%d" % (v, t), generate(v, t, "tight", 1)))
for s in range(1, 4):
    models.append(("facility 6/8 seed %d" % s, facility(6, 8, s, varied=(s == 2))))
for s in range(6):
    models.append(("mixed seed %d" % s, mixed(s)))

warm_total = 0
for name, text in models:
    d, p = prof(text, 256 + 512 + 128)
    if p is None:
        need(False, "%s: no profile in the report (%s)" % (name, d.get("status")))
        continue
    rounds, iters, warm, bad, cold = p[66], p[69], p[70], p[71], p[72]
    if PRINT:
        print("    %r: (%d, %d, %d, %d)," % (name, rounds, p[67], iters, cold))
    need(EXPECTED.get(name) == (rounds, p[67], iters, cold), "%s: (rounds, found, iterations, cold iterations) = %s, exactly %s expected" % (name, (rounds, p[67], iters, cold), EXPECTED.get(name)))
    warm_total += warm
    need(bad == 0, "%s: %d of %d warm solves disagree with the cold solve" % (name, bad, warm))
    retries = p[73]
    need(warm == rounds - 1 - retries, "%s: %d warm solves in %d rounds with %d cold retries (all but the first and the retries are warm)" % (name, warm, rounds, retries))
    if name in ("tight 10x12", "tight 12x12"):
        need(rounds > 20, "%s: only %d rounds, the instance no longer exercises the claim" % (name, rounds))
        need(iters * 5 <= cold, "%s: warm %d iterations against cold %d (at most a fifth required)" % (name, iters, cold))
        d1, p1 = prof(text, 256 + 1024 + 128)
        need(p1 is not None and p1[70] == 0 and p1[69] >= 5 * iters, "%s: bit 1024 does not give the cold counts (%s)" % (name, p1 and (p1[69], p1[70])))
need(warm_total > 0, "no warm solve ran on any instance")

if fails:
    print("warm gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("warm gate: passed (%d checks, %d warm solves compared with cold ones, 0 failures)" % (checks, warm_total))
