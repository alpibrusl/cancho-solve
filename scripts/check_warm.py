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


NORESTART = 134217728    # experiment bit 134217728 * 1: no restarts of the root rounds from perturbed costs (design.md 22.15); the pins below are of the rounds alone, as before them


def prof(text, exp, restarts=False):
    d, _ = solve(text, ["--experiment", str(exp + (0 if restarts else NORESTART)), "--node-limit", "1"])
    return d, (d.get("stats", {}).get("prof") if isinstance(d, dict) else None)


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


# (rounds, cuts found, iterations of the rounds, iterations of their cold solves, cut rows removed by aging) per instance, measured once with `python3 scripts/check_warm.py --print` and held exactly: the rounds are deterministic, and these
# are what notice a change in the weights, in what is counted or in what the LP reports (a mutant that only moves the iterations or the stopping of the rounds)
EXPECTED = {
    'tight 6x8': (24, 59, 481, 1284, 0),
    'tight 8x10': (68, 261, 1835, 8590, 0),
    'tight 10x12': (152, 651, 1938, 36485, 0),
    'tight 12x12': (132, 803, 8143, 57191, 0),
    'tight 8x10 cap1': (53, 220, 1005, 6287, 120),
    'tight 10x12 cap1': (292, 911, 5649, 68555, 653),
    'tight 12x12 cap1': (130, 937, 7478, 49095, 635),
    'facility 6/8 seed 1': (1, 0, 21, 0, 0),
    'facility 6/8 seed 2': (3, 9, 44, 22, 0),
    'facility 6/8 seed 3': (8, 65, 71, 180, 0),
    'mixed seed 0': (1, 0, 7, 0, 0),
    'mixed seed 1': (1, 0, 8, 0, 0),
    'mixed seed 2': (3, 1, 18, 9, 0),
    'mixed seed 3': (4, 4, 22, 21, 0),
    'mixed seed 4': (3, 1, 15, 7, 0),
    'mixed seed 5': (3, 11, 14, 9, 0),
}
# the same instances without the presolve (bit 33554432, design.md 22.12.3), as measured before it became the default: the warm load then copies the values of columns the presolve would have fixed
EXPECTED_NP = {
    'tight 6x8': (23, 68, 333, 1343, 0),
    'tight 8x10': (39, 218, 1058, 7415, 0),
    'tight 10x12': (132, 687, 5088, 45939, 0),
    'tight 12x12': (122, 803, 7341, 55084, 0),
    'tight 8x10 cap1': (39, 218, 1058, 7415, 0),
    'tight 10x12 cap1': (140, 733, 2467, 42373, 417),
    'tight 12x12 cap1': (155, 968, 7601, 63238, 511),
    'facility 6/8 seed 1': (1, 0, 21, 0, 0),
    'facility 6/8 seed 2': (3, 9, 44, 22, 0),
    'facility 6/8 seed 3': (8, 65, 71, 180, 0),
    'mixed seed 0': (1, 0, 10, 0, 0),
    'mixed seed 1': (1, 0, 10, 0, 0),
    'mixed seed 2': (4, 4, 32, 30, 0),
    'mixed seed 3': (4, 5, 29, 27, 0),
    'mixed seed 4': (3, 1, 17, 8, 0),
    'mixed seed 5': (6, 19, 41, 61, 0),
}
NOPRE = 33554432
PRINT = "--print" in sys.argv
AGING = 65536        # experiment bit: cuts age out (opt-in, design.md 22.5; the default keeps every cut)
CAP1 = 131072        # the cut rows may not outnumber the model's own rows before aged ones leave (the default is twice)
models = []
for v, t in [(6, 8), (8, 10), (10, 12), (12, 12)]:
    models.append(("tight %dx%d" % (v, t), generate(v, t, "tight", 1)))
for v, t in [(8, 10), (10, 12), (12, 12)]:
    models.append(("tight %dx%d cap1" % (v, t), generate(v, t, "tight", 1)))
for s in range(1, 4):
    models.append(("facility 6/8 seed %d" % s, facility(6, 8, s, varied=(s == 2))))
for s in range(6):
    models.append(("mixed seed %d" % s, mixed(s)))

warm_total = 0
for pre, EXP in ((0, EXPECTED), (NOPRE, EXPECTED_NP)):
  for name, text in models:
      d, p = prof(text, 256 + 512 + 128 + (AGING + CAP1 if name.endswith("cap1") else 0) + pre)
      if p is None:
          need(False, "%s: no profile in the report (%s)" % (name, d.get("status")))
          continue
      rounds, iters, warm, bad, cold = p[66], p[69], p[70], p[71], p[72]
      if PRINT:
          print("    %r: (%d, %d, %d, %d, %d)," % (name, rounds, p[67], iters, cold, p[74]))
      need(EXP.get(name) == (rounds, p[67], iters, cold, p[74]), ("no presolve " if pre else "") + "%s: (rounds, found, iterations, cold iterations, rows removed) = %s, exactly %s expected" % (name, (rounds, p[67], iters, cold, p[74]), EXP.get(name)))
      warm_total += warm
      need(bad == 0, "%s: %d of %d warm solves disagree with the cold solve" % (name, bad, warm))
      retries = p[73]
      need(warm == rounds - 1 - retries, "%s: %d warm solves in %d rounds with %d cold retries (all but the first and the retries are warm)" % (name, warm, rounds, retries))
      if name in ("tight 10x12", "tight 12x12") and not pre:
          need(rounds > 20, "%s: only %d rounds, the instance no longer exercises the claim" % (name, rounds))
          need(iters * 5 <= cold, "%s: warm %d iterations against cold %d (at most a fifth required)" % (name, iters, cold))
          d1, p1 = prof(text, 256 + 1024 + 128)
          need(p1 is not None and p1[70] == 0 and p1[69] >= 5 * iters, "%s: bit 1024 does not give the cold counts (%s)" % (name, p1 and (p1[69], p1[70])))
# the default (two restarts after the rounds, 22.15): every warm solve of every run still agrees with the cold one, and the first round of each of the three runs is cold
for name, text in models:
    if name.endswith("cap1"):
        continue
    d, p = prof(text, 256 + 512 + 128, restarts=True)
    need(p is not None and p[71] == 0 and p[70] > 0 or (p is not None and p[66] <= 3), "%s: with the restarts, %s disagreements and %s warm solves in %s rounds" % (name, p and p[71], p and p[70], p and p[66]))
    if p is not None and p[66] > 3:
        need(p[70] == p[66] - 3 - p[73], "%s: with the restarts, %d warm solves in %d rounds with %d cold retries (all but the first of each of three runs and the retries are warm)" % (name, p[70], p[66], p[73]))
need(warm_total > 0, "no warm solve ran on any instance")

# G4 aging (design.md 22.5): rows leave on the tight models with the cap of one and on 24 x 16 with the defaults, and never when bit 65536 keeps every cut
for name in ("tight 10x12 cap1", "tight 12x12 cap1"):
    need(EXPECTED[name][4] > 0, "%s: no row left the model, the removal is not exercised" % name)
d, p = prof(generate(10, 12, "tight", 1), 256 + 128 + CAP1)
need(p is not None and p[74] == 0, "10x12 without the aging bit: %s rows removed, none expected" % (p and p[74]))
big = generate(24, 16, "tight", 1)
# the rounds go on while they lift (mutant 43 of mutants_cmir.py): 24 x 16 seed 1 runs to the limit of 300 rounds, 301 counting the first, with the default stall limit of 150
d, p = prof(big, 256 + 128)
need(p is not None and (p[66], p[67], p[68]) == (301, 5213, 327), "24x16 seed 1, the default rounds: (rounds, cuts found, kept) = %s, (301, 5213, 327) expected" % (p and (p[66], p[67], p[68]),))
d, p = prof(big, 256 + 128 + AGING)
need(p is not None and p[74] > 1000 and p[66] <= 301, "24x16 with aging: %s rows removed in %s rounds" % (p and p[74], p and p[66]))
need(d.get("bound", 0) >= 172.82, "24x16 with aging: the root bound after the rounds is %s, at least 172.82 expected (172.825 with aging, 172.915 with every cut kept)" % d.get("bound"))
need(p is not None and p[69] <= 20000, "24x16 with aging: %s iterations in the rounds (about 18,700 expected, 46,277 with every cut kept; with the presolve, design.md 22.12.3)" % (p and p[69]))

if fails:
    print("warm gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("warm gate: passed (%d checks, %d warm solves compared with cold ones, 0 failures)" % (checks, warm_total))
