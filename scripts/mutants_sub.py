#!/usr/bin/env python3
"""Mutants of the cut rounds inside the sub-MIPs (`lp_round`, `mir_rounds` and the call in `drive`, lib/mip/mip.cho, docs/design.md 22.9). Each mutant is built in a scratch copy of the
repository and is killed when one of the gates that can see a wrong answer or a moved path fails (check_sub.py, check_warm.py, check_mir.py); one that builds and
passes all of them is a survivor and must be explained in design.md (22.9). Needs CANCHO=the compiler, and numpy and scipy for the gates.
Usage: CANCHO=... python3 scripts/mutants_restore.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
M = "lib/mip/mip.cho"
GATES = [["scripts/check_sub.py"], ["scripts/check_warm.py"], ["scripts/check_mir.py"]]
MUTANTS = [
    (M, "            le.set_bounds(1, w, wi, m, n, jb, sdb[jb], sdb[n + jb]);\n", "", "the LP of a sub-MIP's rounds ignores its bounds"),
    (M, "                                    sfv[jc] = sdb[jc];\n", "", "the separation ignores the sub-MIP's lower bounds"),
    (M, "                                    sfv[n + jc] = sdb[n + jc];\n", "", "the separation ignores the sub-MIP's upper bounds"),
    (M, "                                    sfv[jc] = sdb[jc];\n                                    sfv[n + jc] = sdb[n + jc];", "                                    sfv[jc] = sdb[n + jc];\n                                    sfv[n + jc] = sdb[jc];", "the sub-MIP's bounds are given to the separation the wrong way round"),
    (M, "        mcap = m0 + 1500;\n", "        mcap = m0 + 1;\n", "a sub-MIP's rounds have no room for cuts"),
    (M, "contents(s1), true, true, 15, 0);", "contents(s1), true, true, 1, 0);", "a sub-MIP's rounds stop after one"),
    (M, "                                                if opts[4] / 4194304 % 2 == 0 {\n                                                    // the sub-MIP gets", "                                                if opts[4] / 4194304 % 2 == 1 {\n                                                    // the sub-MIP gets", "the bit that turns the rounds off turns them on"),
    (M, "                                                                stats[87] = stats[87] + contents(r3)[76];\n", "", "the rounds of the sub-MIPs are not counted"),
    (M, "                                                                while qq < l.ints_len() {\n                                                                    iv2[qq] = ints[qq];", "                                                                while qq < 10 {\n                                                                    iv2[qq] = ints[qq];", "the private copy of the model is cut short"),
    (M, "                                                                c2 = sub_in(heap, iv2, fv2, xv, sv, fv, ov, contents(s1), cv);", "                                                                c2 = sub_in(heap, ints, fl, xv, sv, fv, ov, contents(s1), cv);", "the sub-MIP runs on the model without its cuts"),
    (M, "        code = le.refresh(1, w, wi, fi, ff, m, n);\n        if code == 0 {\n            if le.make_dual_feasible(1, w, wi, m, n) > 0 {\n                code = le.refresh(1, w, wi, fi, ff, m, n);\n            }\n        }\n    }\n    if code == 0 {\n        code = le.run(1, w, wi, fi, ff, st, m, n, 1000000000);", "        code = le.refresh(1, w, wi, fi, ff, m, n);\n    }\n    if code == 0 {\n        code = le.run(1, w, wi, fi, ff, st, m, n, 1000000000);", "(equivalent) the columns on the wrong side are not moved after a sub-MIP's bounds; the rounds use the sparse engine, whose `recompute` repairs them itself (design.md 22.6.1)"),
    (M, "        nnzcap = ints2[l.row_start(m0)] + 60000;\n", "        nnzcap = ints2[l.row_start(m0)] + 1;\n", "a sub-MIP's rounds have no room for the nonzeros of cuts"),
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
