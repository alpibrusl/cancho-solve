#!/usr/bin/env python3
"""Gate 22 (docs/design.md 22.18): `--exp trace` reports where the cut rounds of the root lifted the bound: `stats.trace`, a list of [round, bound], the first LP and then every round whose LP value
differs from the last one listed by at least 1e-7 (at most 50), the round counted over all the runs of the root (restarts included). Written before the code; it fails on a build without the name (G1) and on one
that lists the wrong rounds or values (G2, G3).
G1 present only when asked: with the name, `stats.trace` is a non-empty list of pairs on a tight 8 x 10 model; without it the key is absent and the rest of the report is the same bytes.
G2 the values: with no restart (`restarts=0`) the rounds are one run and the bounds never decrease (minimising, 1e-9 relative), each differs from the one before by at least 1e-7, the rounds are increasing and start at 1, there are
   several entries (the rounds lift this model), and the last bound is the root bound of the report after the rounds (1e-6 relative).
G3 the count: the number of rounds in the last entry is at most `prof[66]` (the rounds of all the runs, `--exp profile`); with the default restarts the entries up to the rounds of the first run are the trace without restarts (the first run is the same run), and a restart's first LP, of perturbed costs, is listed though it is below the entry before (measured on this model).
G4 deterministic: two runs, the same bytes; and a model the rounds do not touch (an LP-sized MIP) gives a report without a trace and without a crash.
Usage: SOLVE=build/solve LAB=build/lab python3 scripts/check_trace.py"""
import json, os, subprocess, sys

SOLVE = os.environ.get("SOLVE", "build/solve")
LAB = os.environ.get("LAB", "build/lab")
fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run(argv, text):
    p = subprocess.run([SOLVE, "run"] + argv, input=text, capture_output=True, text=True, timeout=300)
    return p.stdout, (json.loads(p.stdout) if p.stdout else None)


for exe in (SOLVE, LAB):
    if not os.path.exists(exe):
        print("FAIL no %s" % exe)
        sys.exit(1)
text = subprocess.run([LAB, "gen", "ev", "8", "10", "tight", "1"], capture_output=True, text=True).stdout
ONE = ["--node-limit", "1"]

# G1
raw, d = run(ONE + ["--exp", "eager-rounds,trace"], text)
tr = d["stats"].get("trace") if d else None
need(isinstance(tr, list) and len(tr) > 0 and all(isinstance(e, list) and len(e) == 2 for e in tr), "trace: %s" % (tr,))
raw0, d0 = run(ONE + ["--exp", "eager-rounds"], text)
need("trace" not in d0["stats"], "trace present without the name")
if tr is not None:
    d2 = json.loads(raw)
    del d2["stats"]["trace"]
    need(d2 == d0, "the report with trace, less the trace, is not the report without it")

# G2
raw, d = run(ONE + ["--exp", "eager-rounds,restarts=0,trace,profile"], text)
tr = d["stats"].get("trace", [])
need(len(tr) >= 5, "only %d entries: the rounds lift this model on several rounds" % len(tr))
need(all(tr[k][0] < tr[k + 1][0] for k in range(len(tr) - 1)) and (tr and tr[0][0] == 1), "rounds not increasing from 1: %s" % tr[:6])
need(all(tr[k + 1][1] >= tr[k][1] - 1e-9 * (1 + abs(tr[k][1])) for k in range(len(tr) - 1)), "the bound goes down: %s" % tr)
need(all(abs(tr[k + 1][1] - tr[k][1]) >= 1e-7 - 1e-9 for k in range(len(tr) - 1)), "two entries closer than 1e-7: %s" % tr)
need(tr and abs(tr[-1][1] - d["bound"]) <= 1e-6 * (1 + abs(d["bound"])), "last %s, root bound %s" % (tr[-1] if tr else None, d["bound"]))

# G3
rounds = d["stats"]["prof"][66]
need(len(tr) < 50 and tr[-1][0] <= rounds, "last round %s above the %d rounds" % (tr[-1][0] if tr else None, rounds))
raw, d = run(ONE + ["--exp", "eager-rounds,trace,profile"], text)
tr2 = d["stats"].get("trace", [])
need(tr2 and tr2[-1][0] <= d["stats"]["prof"][66] and d["stats"]["prof"][66] > rounds, "with the restarts: last %s, %d rounds without, %d with" % (tr2[-1][0] if tr2 else None, rounds, d["stats"]["prof"][66]))
need([e for e in tr2 if e[0] <= rounds] == tr, "the first run of the restarts' trace differs from the trace without restarts: %s against %s" % ([e for e in tr2 if e[0] <= rounds], tr))

need(any(tr2[k + 1][1] < tr2[k][1] for k in range(len(tr2) - 1)), "no downward step with the restarts: a perturbed run starts from the LP of its own costs, measured 42.090015423 then 42.090014409 on this model: %s" % tr2)

# G4
a, _ = run(ONE + ["--exp", "eager-rounds,trace"], text)
b, _ = run(ONE + ["--exp", "eager-rounds,trace"], text)
need(a == b, "two runs differ")
small = "var x[0..2] : bool;\nmaximize v: x[0] + x[1];\nsubject to\n    c: x[0] + x[1] <= 1;\n"
raw, d = run(["--exp", "trace"], small)
need(d is not None and d["status"] == "optimal" and "trace" not in d["stats"], "a tiny MIP with trace: %s" % raw[:120])

if fails:
    print("trace gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("trace gate: passed (%d checks, 0 failures)" % checks)
