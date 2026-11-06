#!/usr/bin/env python3
"""Mutants of the restore from the previous node's state (lib/mip/lpeng.cho `make_dual_feasible` and the restore in lib/mip/mip.cho, docs/design.md 22.6). Each mutant is built in a scratch copy of the
repository and is killed when one of the gates that can see a wrong answer or a moved path fails (check_mip_engines.py, check_mip.py, check_nodes.py, both engines for the last); one that builds and
passes all of them is a survivor and must be explained in design.md (22.6). Needs CANCHO=the compiler, and numpy and scipy for the gates.
Usage: CANCHO=... python3 scripts/mutants_restore.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
L = "lib/mip/lpeng.cho"
M = "lib/mip/mip.cho"
GATES = [["scripts/check_mip_engines.py"], ["scripts/check_nodes.py"], ["scripts/check_mip.py"]]
MUTANTS = [
    (M, "if le.make_dual_feasible(eng, w, wi, m, n) > 0 {", "if false {", "the columns on the wrong side are not moved"),
    (M, "                            if le.make_dual_feasible(eng, w, wi, m, n) > 0 {\n                                st = le.refresh(eng, w, wi, fi, ff, m, n);\n                            }", "                            le.make_dual_feasible(eng, w, wi, m, n);", "the values are not recomputed after the columns moved"),
    (M, "if st == 0 && !inplace && exper / 2097152 % 2 == 0 {", "if st == 0 && inplace && exper / 2097152 % 2 == 0 {", "the columns are only made dual feasible after a plunge"),
    (L, "if a == 0 && rc < -1e-9 && hi < 1e20 {", "if a == 0 && rc > 1e-9 && hi < 1e20 {", "a column at its lower bound moves when its reduced cost is right"),
    (L, "} else if a == 1 && rc > 1e-9 && lo > -1e20 {", "} else if a == 1 && rc < -1e-9 && lo > -1e20 {", "a column at its upper bound moves when its reduced cost is right"),
    (L, "if a == 0 && rc < -1e-9 && hi < 1e20 {", "if a == 0 && rc < -1e-9 {", "(equivalent) a column may move to an infinite bound; the bounds of the columns that branching changes are finite, and so are those of the others in the gates' models"),
    (L, "                lo = w[wi[19] + j];\n                hi = w[wi[20] + j];", "                lo = w[wi[20] + j];\n                hi = w[wi[19] + j];", "(equivalent) the sparse engine's bounds are read the wrong way round; its `recompute` repairs a column on the wrong side itself (design.md 22.6), so the flip is redundant there"),
    (L, "                lo = w[o_v + (n + m) + j];\n                hi = w[o_v + 2 * (n + m) + j];", "                lo = w[o_v + 2 * (n + m) + j];\n                hi = w[o_v + (n + m) + j];", "the dense engine's bounds are read the wrong way round"),
    (L, "                    wi[wi[10] + j] = to;\n                    w[wi[18] + j] = bv;", "                    wi[wi[10] + j] = to;", "(equivalent) the sparse engine's column changes side but keeps its value; the same repair in `recompute` sets it"),
    (L, "                    wi[m + n + m + j] = to;\n                    w[o_v + j] = bv;", "                    wi[m + n + m + j] = to;", "the dense engine's column changes side but keeps its value"),
    (L, "            if to >= 0 {\n                var bv = lo;", "            if to >= 5 {\n                var bv = lo;", "no column is ever moved"),
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
        dead = False
        for g in GATES:
            for method in ("dense", "sparse") if g[0].endswith("check_nodes.py") else (None,):
                env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"))
                if method:
                    env["SOLVE_METHOD"] = method
                if subprocess.run([py, os.path.join(tmp, g[0])], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0:
                    dead = True
                    break
            if dead:
                break
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
