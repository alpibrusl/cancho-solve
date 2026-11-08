#!/usr/bin/env python3
"""Mutants of the trace of the cut rounds (lib/mip/mip.cho `trace_note` and its report in tools/solve/emit.cho, docs/design.md 22.18), judged by scripts/check_trace.py. Each mutant is built in a scratch copy of
the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md. Needs CANCHO=the compiler and build/lab.
Usage: CANCHO=... python3 scripts/mutants_trace.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
M = "lib/mip/mip.cho"
E = "tools/solve/emit.cho"
MUTANTS = [
    (M, "    if moved && k < 50 {\n", "    if k < 50 {\n", "every round is listed, not only those that moved"),
    (M, "q - stats[99 + 2 * k] >= 100 || stats[99 + 2 * k] - q >= 100", "q - stats[99 + 2 * k] >= 100", "a move down is not listed"),
    (M, "q - stats[99 + 2 * k] >= 100 || stats[99 + 2 * k] - q >= 100", "q - stats[99 + 2 * k] >= 100000000 || stats[99 + 2 * k] - q >= 100000000", "a move has to be 0.1"),
    (M, "    stats[97] = stats[97] + 1;\n", "", "the rounds are not counted"),
    (M, "        stats[100 + 2 * k] = stats[97];\n", "        stats[100 + 2 * k] = k;\n", "the entry's round is its position"),
    (M, "        stats[101 + 2 * k] = q;\n", "        stats[101 + 2 * k] = q + 1000;\n", "the value is stored a little off"),
    (M, "    var q = truncate(vv * 1000000000.0 + 0.5);\n", "    var q = truncate(vv * 100000000.0 + 0.5);\n", "the value is stored times 1e8"),
    (M, "                                        trace_note(stats, xv[n]);\n", "                                        trace_note(stats, xv[n] + 1.0);\n", "the value traced is not the LP's"),
    (M, "    if len(stats) < 208 {\n        return 0;\n    }\n    stats[97]", "    if len(stats) < 108 {\n        return 0;\n    }\n    stats[97]", "(equivalent) a sub-MIP's stats is thought to have room: the stats of the sub-MIPs have 88 entries and the root's 208, nothing between"),
    (M, "                                    if okc && opts[4] / 67108864 % 2 == 1 {\n", "                                    if okc && opts[4] / 33554432 % 2 == 1 {\n", "the trace reads the bit of the presolve"),
    (E, "            w = json.put_float(heap, w, float_of(stats[101 + 2 * tk]) / 1000000000.0);\n", "            w = json.put_float(heap, w, float_of(stats[101 + 2 * tk]) / 100000000.0);\n", "the report scales the value by 1e8"),
    (E, "    if len(stats) >= 208 && stats[99] > 0 {\n", "    if len(stats) >= 208 {\n", "a trace key is printed with no entry"),
    (E, "            w = json.put_int(heap, w, stats[100 + 2 * tk]);\n", "            w = json.put_int(heap, w, tk);\n", "the report prints the position as the round"),
    (E, "        while tk < stats[99] {\n", "        while tk < stats[99] - 1 {\n", "the report leaves out the last entry"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
lab = os.path.abspath("build/lab")
killed = survived = invalid = 0
for n, (F, old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts"):
            shutil.copytree(d, os.path.join(tmp, d))
        shutil.copy("cancho.toml", tmp)
        f = os.path.join(tmp, F)
        text = open(f).read()
        if old not in text:
            print(f"INVALID mutant {n} ({what}): the text to change is not in {F}")
            invalid += 1
            continue
        open(f, "w").write(text.replace(old, new, 1))
        b = subprocess.run([CANCHO, "build", "--bin", "solve"], capture_output=True, text=True, cwd=tmp)
        if b.returncode != 0:
            print(f"INVALID mutant {n} ({what}): does not build: {(b.stderr or b.stdout).strip()[:200]}")
            invalid += 1
            continue
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), LAB=lab)
        dead = subprocess.run([py, os.path.join(tmp, "scripts", "check_trace.py")], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
