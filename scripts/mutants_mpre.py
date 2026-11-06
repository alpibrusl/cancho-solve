#!/usr/bin/env python3
"""Mutants of the presolve of the MIP search (lib/mip/mpre.cho and its calls in lib/mip/mip.cho, docs/design.md 22.12). Each mutant is built in a scratch copy of the repository and is killed when
check_mpre.py fails (it holds the counts of the hand models, the answers of 107 generated models against HiGHS and the 24 x 16 effect); one that builds and passes it is a survivor and must be explained
in design.md (22.12.1). Needs CANCHO=the compiler, and numpy and scipy for the gate (run it with the python that has them).
Usage: CANCHO=... python3 scripts/mutants_mpre.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
P = "lib/mip/mpre.cho"
M = "lib/mip/mip.cho"
GATES = [["scripts/check_mpre.py"]]
MUTANTS = [
    (P, "                } else if amin >= rlo - tol(rlo) && amax <= rhi + tol(rhi) {\n", "                } else if false {\n", "no row is ever redundant"),
    (P, "                } else if amin >= rlo - tol(rlo) && amax <= rhi + tol(rhi) {\n", "                } else if amin >= rlo - tol(rlo) {\n", "a row is redundant when only its lower side holds"),
    (P, "                } else if amin > rhi + tol(rhi) || amax < rlo - tol(rlo) {\n", "                } else if amin > rhi + tol(rhi) {\n", "(equivalent) the upper activity bound does not prove infeasibility: the row stays and the search proves the model infeasible; the answer is the same"),
    (P, "                        if !(a > 0.0 && nolo || a < 0.0 && nohi) {\n                            scr[jc] = 1;\n                        }\n", "", "lowering a column is never blocked by a row"),
    (P, "                        if !(a > 0.0 && nohi || a < 0.0 && nolo) {\n                            scr[n + jc] = 1;\n                        }\n", "", "raising a column is never blocked by a row"),
    (P, "                if cf[j] >= 0.0 && scr[j] == 0 {", "                if cf[j] >= 0.0 {", "a column with a nonnegative cost is fixed low whatever its rows say"),
    (P, "            cf[jo] = cf[jo] + sg * fl[l.obj_coef(t0)];", "            cf[jo] = cf[jo] + fl[l.obj_coef(t0)];", "the sign of a maximisation is ignored by the dual fixing"),
    (P, "                    fx = fx + a * bnd[jc];\n                } else {\n                    ints[l.term_col(nnz + cnt)]", "                    fx = fx;\n                } else {\n                    ints[l.term_col(nnz + cnt)]", "a substituted column's term is lost from the right side"),
    (P, "        s0 = e0;\n", "        s0 = ints[l.row_start(r + 1)];\n", "the start of the next row is read after it may have been overwritten"),
    (P, "                    if nl > nh + tol(nh) {", "                    if nl > nh + 1e9 {", "a singleton row whose bound crosses the others is not infeasible"),
    (P, "                    if rlo > tol(rlo) && rlo > -1e299 || rhi < 0.0 - tol(rhi) && rhi < 1e299 {\n                        infeasible = true;\n                    }\n", "", "an empty row is never infeasible"),
    (P, "                } else if live == 1 && mag(al) > 1e-9 {", "                } else if live == 1000 && mag(al) > 1e-9 {", "a singleton row is not turned into a bound"),
    (P, "    while changed && sweep < 20 && !infeasible {", "    while changed && sweep < 1 && !infeasible {", "one sweep only"),
    (P, "                            l2 = 0.0 - floor_of(0.0 - (l2 - 1e-9));", "                            l2 = l2;", "an integer column's lower bound from a row is not rounded up"),
    (P, "                        h2 = floor_of(h2 + 1e-9);", "                        h2 = h2;", "an integer column's upper bound from a row is not rounded down"),
    (M, "                                    stats[55] = contents(b8)[0];\n", "", "the rows dropped are not reported"),
    (M, "                                        if mp.compact(iv, fv, contents(b5), contents(b3)) < 0 {", "                                        if false {", "the rows are not compacted away"),
    (M, "            ctl[3] = 1;\n        }\n", "        }\n", "the root of the main search ignores the presolve's bounds"),
    (M, "                sd[jq] = pb[jq];\n", "                sd[jq] = sd[jq];\n", "the base bounds of the searches are the model's"),
    (M, "mir_rounds(heap, iv, fv, opts, stats, pb, usepb, false, 300);", "mir_rounds(heap, iv, fv, opts, stats, pb, false, false, 300);", "(equivalent in effect) the first cut rounds ignore the presolve's bounds: on 24 tight models the rounds, the cuts found and kept and the root bound are identical, the rounds never meet a tightened bound"),
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
