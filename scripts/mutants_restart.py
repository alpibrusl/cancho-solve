#!/usr/bin/env python3
"""Mutants of the root restarts of the cut rounds (mir_multi and the perturbation in mir_rounds, lib/mip/mip.cho, docs/design.md 22.15), judged by scripts/check_restart.py, then check_warm.py and check_mir.py. Each mutant is
built in a scratch copy of the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md (22.3). Needs CANCHO=the compiler.
Usage: CANCHO=... python3 scripts/mutants_restart.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
R = "lib/lp/revised.cho"
M = "lib/mip/mip.cho"
MUTANTS = [
    (M, "    var restarts = 2;\n", "    var restarts = 0;\n", "no restart by default"),
    (M, "    var restarts = 2;\n", "    var restarts = 1;\n", "one restart by default"),
    (M, "        restarts = v - 1;\n", "        restarts = v;\n", "the bit gives one restart too many"),
    (M, "    let perturb = pseed > 0;\n", "    let perturb = false;\n", "the restarts run on the true costs"),
    (M, "                let u = ((pt + 1) * 1103515245 * pseed + 12345 * pseed) % 65536;\n", "                let u = ((pt + 1) * 1103515245 + 12345) % 65536;\n", "every restart perturbs the costs the same way"),
    (M, "(1.0 + 0.000001 * float_of(u) / 65536.0)", "(1.0 + 0.001 * float_of(u) / 65536.0)", "the perturbation is a thousand times larger"),
    (M, "                fl2[l.obj_coef(pt2)] = ov2[pt2];\n", "", "the costs are not restored after a restart"),
    (M, "        kept = kept + mir_rounds(heap, ints2, fl2, opts, stats, sdb, subb, false, 300, rs);\n", "        kept = mir_rounds(heap, ints2, fl2, opts, stats, sdb, subb, false, 300, rs);\n", "the rows kept by the earlier runs are forgotten in the count"),
    (M, "        rounds = rounds + stats[76];\n", "", "the rounds of the restarts are not counted"),
    (M, "        found = found + stats[77];\n", "", "the cuts found by the restarts are not counted"),
    (M, "    var kept = mir_rounds(heap, ints2, fl2, opts, stats, sdb, subb, false, 300, 0);\n", "    var kept = mir_rounds(heap, ints2, fl2, opts, stats, sdb, subb, false, 300, 1);\n", "the first run is perturbed too"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
killed = survived = invalid = 0
for n, (F, old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts", "tests", "docs"):
            if d == "docs":
                os.makedirs(os.path.join(tmp, "docs"))
                shutil.copytree("docs/examples", os.path.join(tmp, "docs", "examples"))
            else:
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
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"))
        dead = any(subprocess.run([py, os.path.join(tmp, "scripts", g)], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0 for g in ("check_restart.py", "check_warm.py", "check_mir.py"))
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
