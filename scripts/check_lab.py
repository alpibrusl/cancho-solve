#!/usr/bin/env python3
"""Gate 20 (docs/design.md 22.18): `lab gen ev V T SETTING SEED` prints the bytes of `evgen.generate(V, T, SETTING, SEED)`, so that a model of the gates is made without Python.
Written before `tools/lab`; it fails on a build that is not there (G0), on a generator that differs in one byte (G1), and on an input outside what the generator can promise (G2).
G1 bytes: 12 (V, T, setting, seed) tuples, among them 24 x 16 seed 14 (the model of 22.17), an odd V (the grid at a half-integer, rounded to even), and a seed whose key needs two
   32-bit limbs; and every T from 2 to 60 at V = 2 (the price column: `round(x, 2)` and the shortest decimal of a Python float).
G2 refusals: V below 1, T below 2, a setting that is neither `ample` nor `tight`, a word where a number is expected: exit status 2, nothing on standard output, a `lab.usage` tag on standard error.
Usage: LAB=build/lab python3 scripts/check_lab.py"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evgen import generate

LAB = os.environ.get("LAB", "build/lab")
fails = []
checks = 0


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def lab(argv):
    return subprocess.run([LAB] + argv, capture_output=True, text=True, timeout=60)


if not os.path.exists(LAB):
    print("FAIL no %s: build it with `cancho build --bin lab`" % LAB)
    sys.exit(1)

TUPLES = [(6, 8, "tight", 1), (10, 12, "tight", 1), (12, 12, "ample", 3), (15, 12, "tight", 2), (24, 16, "tight", 14), (24, 16, "tight", 9),
          (16, 12, "tight", 8), (24, 16, "ample", 4), (7, 5, "tight", 5), (2, 2, "tight", 1), (30, 24, "tight", 4000), (30, 24, "tight", 123457)]
for v, t, s, seed in TUPLES:
    p = lab(["gen", "ev", str(v), str(t), s, str(seed)])
    need(p.returncode == 0 and p.stdout == generate(v, t, s, seed), "ev %d %d %s %d: %s" % (v, t, s, seed, "exit %d" % p.returncode if p.returncode else "bytes differ"))
for t in range(2, 61):
    p = lab(["gen", "ev", "2", str(t), "tight", "1"])
    need(p.returncode == 0 and p.stdout == generate(2, t, "tight", 1), "ev 2 %d tight 1: price column or bytes differ" % t)
for argv in (["gen", "ev", "0", "8", "tight", "1"], ["gen", "ev", "8", "1", "tight", "1"], ["gen", "ev", "8", "8", "loose", "1"], ["gen", "ev", "8", "8", "tight", "x"], ["gen", "ev", "8"], ["gen", "nope"], []):
    p = lab(argv)
    tag = ""
    try:
        tag = json.loads(p.stderr).get("error", "")
    except Exception:
        pass
    need(p.returncode == 2 and p.stdout == "" and tag == "lab.usage", "%s: exit %d, tag %r, expected 2 and lab.usage" % (argv, p.returncode, tag))

if fails:
    print("lab gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("lab gate: passed (%d checks, 0 failures)" % checks)
