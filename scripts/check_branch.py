#!/usr/bin/env python3
"""Gate 10 (docs/design.md 22.8): reliability branching does what is claimed, and the rule it replaced is still there. Written before `reliable_pick`; it fails on a build without it.
G1 effect: the tight 24 x 16 models of seed 7 (the page's) and of seed 1 are proved optimal with the default: 3,000 nodes (SB iterations 14,563, trials 1,361) and 39,085 nodes
   (14,983, 1,253), each held exactly; the optimum is HiGHS's (191.45 and 172.93, computed here). With `--branching pseudo` the page's model needs 24,600 nodes and seed 1 needs 36,750.
   Corrected by 22.12.3 (the presolve is the default): before it, pseudo-costs did not prove the page's model in 30,000 nodes and needed 46,653 on seed 1, so the rule was said to take the nodes down by at least 1.9x on the second
   and to make the first possible. Now the rule takes the nodes of the page's model down by 8.2x (and 1.8x to 2.7x the seconds), and on seed 1 it takes 6 percent more nodes and 1.15x fewer seconds (34.3 s against 39.4 s, one run each).
G2 the old rules stay: `--branching pseudo` and `--branching fractional` are accepted, the first is the rule of 19.2 (no strong-branching trials, `prof[76] == 0`), the default takes trials.
G3 refusal: `--branching nonsense` is refused with exit status 2 and a usage tag.
Needs scipy for HiGHS. Usage: SOLVE=build/solve python3 scripts/check_branch.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate
from gen_models import sh, solve, highs

fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


CASES = [("page 24x16 (seed 7)", generate(24, 16, "tight", 7), 3000, 14563, 1361),
         ("24x16 seed 1", generate(24, 16, "tight", 1), 39085, 14983, 1253)]
for name, text, nodes, sbit, trials in CASES:
    r, _ = solve(text, ["--experiment", "128", "--node-limit", "100000"])
    p = r.get("stats", {}).get("prof")
    need(p is not None and r["status"] == "optimal", "%s: default is %s, optimal expected" % (name, r.get("status")))
    if p is None or r["status"] != "optimal":
        continue
    hs, hv = highs(text)
    need(abs(r["objective"] - hv) <= 1e-6 * (1 + abs(hv)), "%s: objective %s, HiGHS %s" % (name, r["objective"], hv))
    need((r["stats"]["nodes"], p[75], p[76]) == (nodes, sbit, trials), "%s: (nodes, strong-branching iterations, trials) = %s, exactly %s expected" % (name, (r["stats"]["nodes"], p[75], p[76]), (nodes, sbit, trials)))
r, _ = solve(CASES[0][1], ["--experiment", "128", "--branching", "pseudo", "--node-limit", "30000"])
need(r["status"] == "optimal" and r["stats"]["nodes"] == 24600 and r["stats"]["prof"][76] == 0, "page 24x16 with pseudo-costs: %s in %s nodes, %s trials (optimal in 24,600 nodes and no trials expected)" % (r["status"], r["stats"]["nodes"], r["stats"]["prof"][76]))
r, _ = solve(CASES[1][1], ["--branching", "pseudo", "--node-limit", "100000"])
need(r["status"] == "optimal" and r["stats"]["nodes"] == 36750, "24x16 seed 1 with pseudo-costs: %s, %s nodes (optimal in 36,750 expected)" % (r["status"], r["stats"]["nodes"]))
r, _ = solve(CASES[1][1], ["--branching", "fractional", "--node-limit", "2000"])
need(r["status"] in ("feasible", "unknown", "optimal"), "--branching fractional: %s" % r["status"])
q = sh(["run", "--branching", "nonsense"], CASES[0][1])
need(q.returncode == 2 and "solve." in q.stdout + q.stderr, "--branching nonsense: exit %d, %s" % (q.returncode, (q.stdout + q.stderr)[:80]))

if fails:
    print("branch gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("branch gate: passed (%d checks, 0 failures)" % checks)
