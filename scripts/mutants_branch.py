#!/usr/bin/env python3
"""Mutants of reliability branching (`sb_trial`, `reliable_pick` and their call in lib/mip/mip.cho, docs/design.md 22.8). Each mutant is built in a scratch copy of the
repository and is killed when one of the gates that can see a wrong answer or a moved path fails (check_branch.py, check_nodes.py with both engines, check_mip_engines.py); one that builds and
passes all of them is a survivor and must be explained in design.md (22.8). Needs CANCHO=the compiler, and numpy and scipy for the gates.
Usage: CANCHO=... python3 scripts/mutants_restore.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
M = "lib/mip/mip.cho"
GATES = [["scripts/check_branch.py"], ["scripts/check_nodes.py"], ["scripts/check_mip_engines.py"]]
MUTANTS = [
    (M, "    le.set_bounds(eng, w, wi, m, n, j, lo, hi);\n    var st = le.refresh", "    var st = le.refresh", "a trial does not change the bound of its column"),
    (M, "    le.set_bounds(eng, w, wi, m, n, j, bl, bh);\n    var st2", "    var st2", "the bound of the column is not put back after a trial"),
    (M, "    if st2 != sx.s_optimal() {\n        return 0.0 - 2e300;", "    if false {\n        return 0.0 - 2e300;", "a node left unsolved by a trial is not reported"),
    (M, "        st = le.run(eng, w, wi, fi, ff, stats, m, n, lim);\n        stats[85] = stats[85] + stats[0];\n        if st == sx.s_optimal() || st == sx.s_limit() {", "        st = le.run(eng, w, wi, fi, ff, stats, m, n, 1);\n        stats[85] = stats[85] + stats[0];\n        if st == sx.s_optimal() || st == sx.s_limit() {", "a trial runs one iteration"),
    (M, "        st = le.run(eng, w, wi, fi, ff, stats, m, n, lim);\n        stats[85] = stats[85] + stats[0];", "        st = le.run(eng, w, wi, fi, ff, stats, m, n, lim);", "the iterations of a trial are not counted"),
    (M, "            if prunable(zc, have, inc, whole) {\n                zc = 1e300;\n            }", "", "a child cut by the incumbent is not treated as infeasible"),
    (M, "        } else if st == sx.s_infeasible() {\n            zc = 1e300;\n        }", "        }", "an infeasible child is not recognised"),
    (M, "        mf[o_sbv + j] = w[o_v + j];\n        j = j + 1;\n    }\n    var su = 0.0;", "        j = j + 1;\n    }\n    var su = 0.0;", "the LP point of the node is not saved before the trials"),
    (M, "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && budget && done < kmax {", "if (mi[o_pcu + cj] > eta || mi[o_pcd + cj] > eta) && budget && done < kmax {", "only the reliable columns are strong-branched"),
    (M, "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && budget && done < kmax {", "if (mi[o_pcu + cj] < eta && mi[o_pcd + cj] < eta) && budget && done < kmax {", "a column is strong-branched only when both directions are unreliable"),
    (M, "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && budget && done < kmax {", "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && done < kmax {", "(equivalent) the strong-branching budget is ignored; the gates' instances never exhaust it"),
    (M, "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && budget && done < kmax {", "if (mi[o_pcu + cj] < eta || mi[o_pcd + cj] < eta) && budget && done < 1 {", "one candidate at most is strong-branched"),
    (M, "if noimp >= look || (done >= kmax && noimp >= 1) {", "if noimp >= 1 || (done >= kmax && noimp >= 1) {", "the walk ends after one candidate that did not improve"),
    (M, "                let gd = fmax(zd - z, 0.0);", "                let gd = fmax(zu - z, 0.0);", "the gain of the down child is that of the up child"),
    (M, "                mf[o_psd + cj] = mf[o_psd + cj] + gd / fmax(fr, 1e-9);\n", "", "the pseudo-cost of the down direction is not updated by a trial"),
    (M, "                mi[o_pcu + cj] = mi[o_pcu + cj] + 1;\n                score", "                score", "the count of up observations is not updated by a trial"),
    (M, "                mf[o_psu + cj] = mf[o_psu + cj] + gu / fmax(1.0 - fr, 1e-9);", "                mf[o_psu + cj] = mf[o_psu + cj] + gu * fmax(1.0 - fr, 1e-9);", "the up gain is multiplied by its distance instead of divided"),
    (M, "                score = fmax(gd, 1e-6) * fmax(gu, 1e-6);", "                score = fmax(gd, 1e-6) + fmax(gu, 1e-6);", "the score of a strong-branched column is a sum"),
    (M, "                if zd >= 1e299 || zu >= 1e299 {", "                if zd >= 1e299 && zu >= 1e299 {", "a column with one infeasible child does not decide the choice"),
    (M, "                    iters = iters + stats[85] - before;\n", "", "the iterations of the trials are not added to the search's"),
    (M, "if bm == 2 && jb >= 0 && !prunable(z, have, inc, whole) {", "if bm == 1 && jb >= 0 && !prunable(z, have, inc, whole) {", "reliability branching is never used"),
    (M, "                    if sbv {\n                        v = mf[o_sbv + jb];\n                    }", "", "the branching reads the point after the trials, not before"),
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
