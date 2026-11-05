#!/usr/bin/env python3
"""Gate 1 (docs/design.md section 7): every tests/ok file is accepted by `solve check`,
every tests/refused file is refused with the rule named in its `//~ RULE` line."""
import glob, json, os, re, subprocess, sys

SOLVE = os.environ.get("SOLVE", "build/solve")
bad = 0

for path in sorted(glob.glob("tests/ok/*.sol")):
    p = subprocess.run([SOLVE, "check"], stdin=open(path), capture_output=True, text=True)
    if p.returncode != 0:
        print(f"FAIL {path}: expected accepted, status {p.returncode}: {p.stderr.strip()}")
        bad += 1
        continue
    try:
        json.loads(p.stdout)
    except ValueError:
        print(f"FAIL {path}: standard output is not JSON: {p.stdout!r}")
        bad += 1

for path in sorted(glob.glob("tests/refused/*.sol")):
    want = re.search(r"//~ RULE (\S+)", open(path).read()).group(1)
    p = subprocess.run([SOLVE, "check"], stdin=open(path), capture_output=True, text=True)
    try:
        got = json.loads(p.stderr)["error"]
    except (ValueError, KeyError):
        got = None
    if p.returncode != 2 or p.stdout != "" or got != want:
        print(f"FAIL {path}: wanted status 2 and {want}, got status {p.returncode}, {got}")
        bad += 1

print("language gate:", "FAILED" if bad else "passed", f"({bad} failures)")
sys.exit(1 if bad else 0)
