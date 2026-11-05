#!/usr/bin/env python3
"""Gate 2 (docs/design.md section 12): `solve expand` of tests/ok/NAME.sol equals the hand-derived tests/expand/NAME.json, compared as data
(numbers by value), and `solve check` reports the same counts."""
import glob, json, os, subprocess, sys

SOLVE = os.environ.get("SOLVE", "build/solve")
bad = 0

def run(verb, path):
    return subprocess.run([SOLVE, verb], stdin=open(path), capture_output=True, text=True)

for want_path in sorted(glob.glob("tests/expand/*.json")):
    name = os.path.basename(want_path)[:-5]
    src = f"tests/ok/{name}.sol"
    want = json.load(open(want_path))
    p = run("expand", src)
    if p.returncode != 0:
        print(f"FAIL {name}: expand status {p.returncode}: {p.stderr.strip()}")
        bad += 1
        continue
    got = json.loads(p.stdout)
    if got != want:
        print(f"FAIL {name}: expansion differs\n  got  {json.dumps(got)}\n  want {json.dumps(want)}")
        bad += 1
        continue
    c = json.loads(run("check", src).stdout)
    nz = sum(len(r["terms"]) for r in want["constraints"])
    ints = sum(1 for v in want["variables"] if v["kind"] != "real")
    ok = (c["variables"] == len(want["variables"]) and c["constraints"] == len(want["constraints"])
          and c["nonzeros"] == nz and c["integer"] == ints)
    if not ok:
        print(f"FAIL {name}: check disagrees with expand: {c}")
        bad += 1

print("expand gate:", "FAILED" if bad else "passed", f"({bad} failures)")
sys.exit(1 if bad else 0)
