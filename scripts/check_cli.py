#!/usr/bin/env python3
"""Gate 3 (docs/design.md section 7): no input reaches a panic. Every outcome is a result (status 0) or a refusal (status 2 with a rule tag on
standard error and nothing on standard output). Truncations and byte mutations of every corpus file, and random bytes, with a fixed seed."""
import glob, json, os, random, subprocess, sys

SOLVE = os.environ.get("SOLVE", "build/solve")
rng = random.Random(20261104)
bad = runs = 0

def run(data, label, verb=("check",)):
    global bad, runs
    runs += 1
    p = subprocess.run([SOLVE, *verb], input=data, capture_output=True, timeout=60)
    if p.returncode in (0, 1):
        ok = p.stderr == b"" and "status" in json.loads(p.stdout)
    elif p.returncode == 2:
        try:
            ok = p.stdout == b"" and json.loads(p.stderr)["error"].startswith("solve.")
        except ValueError:
            ok = False
    else:
        ok = False
    if not ok:
        bad += 1
        print(f"FAIL {label}: status {p.returncode}, stderr {p.stderr[:200]!r}")

files = [open(f, "rb").read() for f in sorted(glob.glob("tests/*/*.sol"))]
for n, src in enumerate(files):
    for cut in range(0, len(src) + 1, 3):
        run(src[:cut], f"file {n} cut {cut}")
    for _ in range(60):
        b = bytearray(src)
        for _ in range(rng.randint(1, 4)):
            if b:
                b[rng.randrange(len(b))] = rng.choice(b"();:.,*/+-<>=[]{} \n\t\0\xff0129aevx")
        run(bytes(b), f"file {n} mutation")
for _ in range(300):
    run(bytes(rng.randrange(256) for _ in range(rng.randint(0, 80))), "random bytes")
# `run --relax` on cuts and mutations of the small models (no panic; every outcome a result or a refusal)
for n, src in enumerate(files):
    if len(src) < 600:
        for cut in range(0, len(src) + 1, 5):
            run(src[:cut], f"run file {n} cut {cut}", ("run", "--relax"))
            run(src[:cut], f"run file {n} cut {cut} mip", ("run", "--node-limit", "20"))
        for _ in range(20):
            b = bytearray(src)
            for _ in range(rng.randint(1, 3)):
                if b:
                    b[rng.randrange(len(b))] = rng.choice(b"();:.,*/+-<>=[]{} \n\t\0\xff0129aevx")
            run(bytes(b), f"run file {n} mutation", ("run", "--relax"))
            run(bytes(b), f"run file {n} mutation mip", ("run", "--node-limit", "20"))

# the iteration limit: lp_basic needs 2 iterations (3 before the long step of docs/design.md section 17)
lp = open("tests/ok/lp_basic.sol", "rb").read()
for limit, want_status, want_iters, want_code in [(0, "unknown", 0, 1), (1, "unknown", 1, 1), (2, "optimal", 2, 0), (3, "optimal", 2, 0), (1000, "optimal", 2, 0)]:
    runs += 1
    p = subprocess.run([SOLVE, "run", "--iteration-limit", str(limit)], input=lp, capture_output=True)
    r = json.loads(p.stdout)
    if p.returncode != want_code or r["status"] != want_status or r["stats"]["iterations"] != want_iters:
        bad += 1
        print(f"FAIL iteration limit {limit}: status {p.returncode}, {r['status']}, {r['stats']}")
# S3 (docs/design.md section 19): an integer model without --relax is SOLVED now (this used to expect the refusal solve.not-built, deliberately replaced); bad flags are a usage error
runs += 2
p = subprocess.run([SOLVE, "run"], input=open("tests/ok/knapsack.sol", "rb").read(), capture_output=True)
if p.returncode != 0 or json.loads(p.stdout)["status"] != "optimal" or json.loads(p.stdout)["objective"] != 13:
    bad += 1
    print("FAIL integer model without --relax is not solved", p.returncode, p.stdout[:200], p.stderr[:200])
for flags in (["--node-limit", "x"], ["--node-limit"], ["--node-limit", "2000001"], ["--node-select", "worst"], ["--branching", "random"], ["--node-select"]):
    runs += 1
    p = subprocess.run([SOLVE, "run", *flags], input=open("tests/ok/knapsack.sol", "rb").read(), capture_output=True)
    if p.returncode != 2 or json.loads(p.stderr)["error"] not in ("solve.usage", "solve.too-large") or p.stdout != b"":
        bad += 1
        print("FAIL bad MIP flag", flags, p.returncode, p.stderr[:200])
p = subprocess.run([SOLVE, "run", "--bogus"], input=lp, capture_output=True)
if p.returncode != 2 or json.loads(p.stderr)["error"] != "solve.usage":
    bad += 1
    print("FAIL bad flag")

# one variable too many
run(b"".join(b"var v%d : bool;\n" % i for i in range(16400)), "16400 variables")
# very deep parentheses
run(b"var x : real 0..1;\nminimize " + b"(" * 5000 + b"x" + b")" * 5000 + b";", "deep parentheses")

print("cli gate:", "FAILED" if bad else "passed", f"({runs} runs, {bad} failures)")
sys.exit(1 if bad else 0)
