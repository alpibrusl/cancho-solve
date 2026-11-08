#!/usr/bin/env python3
"""Gate 21 (docs/design.md 22.18): `solve run --exp NAME[,NAME[=V]...]` names the experiment bits that `--experiment N` takes as a number, and `solve introspect` lists them.
Written before `tools/solve/exper.cho`; it fails on a build without `--exp` (G1), on a table that disagrees with the one held here (G2), and on spellings that must be refused (G3).
G1 same bytes: for every name, and for combinations, `--exp` gives the bytes of `--experiment` with the number computed here (with the profile bit added, so that the counters of the rounds
   show what the bits did), on a tight 6 x 8 model made by `lab gen`; `restarts=N` is N restarts (field value N + 1, 0 the default of two), `cap=K` and `aging-limit=K` the fields of 22.5.
G2 the table: `introspect` has `experiments`, a list of {name, bit, min, max, offset} in the order held here, exactly (a flag has max 0).
G3 refusals: `gomory-nnz` without `gomory` (22.19), an unknown name, a field without its value, a value out of range, a flag with a value, an empty name, a repeated name, `--exp` twice, `--exp` together with `--experiment`: exit status 2,
   nothing on standard output, `solve.usage` on standard error.
Usage: SOLVE=build/solve LAB=build/lab python3 scripts/check_exp.py"""
import json, os, subprocess, sys

SOLVE = os.environ.get("SOLVE", "build/solve")
LAB = os.environ.get("LAB", "build/lab")
fails = []
checks = 0

# (name, bit, min, max, offset): a flag has max 0; a field is `bit * (value + offset)` for value in min..max
TABLE = [
    ("no-objective-cut", 1, 0, 0, 0), ("no-rounding", 2, 0, 0, 0), ("plunge-far", 4, 0, 0, 0), ("no-implied", 8, 0, 0, 0), ("no-rc-fixing", 16, 0, 0, 0), ("no-pause", 32, 0, 0, 0),
    ("no-mir", 64, 0, 0, 0), ("profile", 128, 0, 0, 0), ("eager-rounds", 256, 0, 0, 0), ("warm-check", 512, 0, 0, 0), ("cold-rounds", 1024, 0, 0, 0),
    ("aging-limit", 4096, 1, 15, 0), ("aging", 65536, 0, 0, 0), ("cap", 131072, 1, 7, 0), ("restore-root", 2097152, 0, 0, 0), ("sub-plain", 4194304, 0, 0, 0),
    ("no-presolve", 33554432, 0, 0, 0), ("restarts", 134217728, 0, 14, 1), ("trace", 67108864, 0, 0, 0), ("gomory", 2147483648, 0, 0, 0),
    ("gomory-nnz", 4294967296, 1, 7, 0),
]


def need(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def run(argv, text):
    return subprocess.run([SOLVE, "run"] + argv, input=text, capture_output=True, text=True, timeout=120)


for exe in (SOLVE, LAB):
    if not os.path.exists(exe):
        print("FAIL no %s" % exe)
        sys.exit(1)
text = subprocess.run([LAB, "gen", "ev", "6", "8", "tight", "1"], capture_output=True, text=True).stdout

# G2
d = json.loads(subprocess.run([SOLVE, "introspect"], capture_output=True, text=True).stdout)
got = [(e["name"], e["bit"], e["min"], e["max"], e["offset"]) for e in d.get("experiments", [])]
need(got == TABLE, "introspect experiments: %s, expected %s" % (got, TABLE))

# G1
NODES = ["--node-limit", "40"]
PROFILE = 128


def same(spec, number):
    a = run(NODES + ["--exp", spec], text)
    b = run(NODES + ["--experiment", str(number)], text)
    need(a.returncode in (0, 1) and a.stdout == b.stdout and a.stdout != "", "--exp %s vs --experiment %d: exit %d, %s" % (spec, number, a.returncode, "same" if a.stdout == b.stdout else "bytes differ"))


for name, bit, lo, hi, off in TABLE:
    if hi == 0:
        same("%s,profile" % name if name != "profile" else "profile", bit | PROFILE)
    else:
        for v in sorted({lo, hi, (lo + hi) // 2}):
            if name == "gomory-nnz":                       # a budget needs the name it budgets (22.19)
                same("gomory,%s=%d,profile" % (name, v), bit * (v + off) | 2147483648 | PROFILE)
            else:
                same("%s=%d,profile" % (name, v), bit * (v + off) | PROFILE)
same("eager-rounds,profile", 384)
same("profile,eager-rounds,restarts=0", 128 + 256 + 134217728)
same("aging,aging-limit=3,cap=2,profile", 65536 + 3 * 4096 + 2 * 131072 + 128)
same("restarts=3,eager-rounds,profile", 134217728 * 4 + 256 + 128)
same("gomory,gomory-nnz=3,profile", 2147483648 + 3 * 4294967296 + 128)
a, b = run(NODES + ["--exp", "profile"], text), run(NODES, text)
need(a.stdout != b.stdout, "--exp profile gives the bytes of no experiment: the table maps nothing")
a = run(NODES + ["--exp", "restarts=0,eager-rounds,profile"], text)
b = run(NODES + ["--exp", "eager-rounds,profile"], text)
need(a.stdout != b.stdout, "restarts=0 gives the bytes of the default's two restarts")

# G3
for spec in ("nope", "restarts", "restarts=15", "restarts=-1", "restarts=x", "profile=1", "", "profile,,aging", "profile,profile", "aging-limit=0", "cap=8", ",", "restarts=", "gomory-nnz=2", "gomory-nnz=0,gomory", "gomory,gomory-nnz=8", "gomory,gomory-nnz"):
    p = run(NODES + ["--exp", spec], text)
    tag = ""
    try:
        tag = json.loads(p.stderr).get("error", "")
    except Exception:
        pass
    need(p.returncode == 2 and p.stdout == "" and tag == "solve.usage", "--exp %r: exit %d, tag %r, expected 2 and solve.usage" % (spec, p.returncode, tag))
p = run(NODES + ["--exp", "profile", "--experiment", "128"], text)
need(p.returncode == 2 and p.stdout == "", "--exp with --experiment: exit %d, expected 2" % p.returncode)
p = run(NODES + ["--exp", "profile", "--exp", "aging"], text)
need(p.returncode == 2 and p.stdout == "", "--exp twice: exit %d, expected 2" % p.returncode)
p = run(NODES + ["--exp"], text)
need(p.returncode == 2 and p.stdout == "", "--exp without a value: exit %d, expected 2" % p.returncode)

if fails:
    print("exp gate: FAILED (%d checks, %d failures)" % (checks, len(fails)))
    sys.exit(1)
print("exp gate: passed (%d checks, 0 failures)" % checks)
