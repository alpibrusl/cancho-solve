#!/usr/bin/env python3
"""Mutants of the presolve (lib/lp/presolve.cho, docs/design.md section 21.3), judged by scripts/check_presolve.py, then check_highs.py and check_dense_vs_sparse.py with
SOLVE_METHOD=sparse. Each mutant is built in a scratch copy; killed when a gate fails. Needs CANCHO=the compiler, PYTHON with numpy+scipy.
Usage: CANCHO=... python3 scripts/mutants_presolve.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
F = "lib/lp/presolve.cho"
MUTANTS = [
    ("let lowok = rlo < -1e299 || amin >= rlo - tol(rlo);", "let lowok = true;", "a row is redundant on its upper activity alone"),
    ("let highok = rhi > 1e299 || amax <= rhi + tol(rhi);", "let highok = true;", "a row is redundant on its lower activity alone"),
    ("if rhi < 1e299 && amin > rhi + tol(rhi) {", "if false {", "(equivalent) a row whose least activity is above its upper side is not infeasible; the other two infeasibility tests catch it (design.md 22.14)"),
    ("if rlo > -1e299 && amax < rlo - tol(rlo) {", "if false {", "(equivalent) a row whose greatest activity is below its lower side is not infeasible; the other two infeasibility tests catch it (design.md 22.14)"),
    ("if nl > lo {", "if nl > 1e300 {", "a singleton row does not raise the lower bound"),
    ("if nh < hi {", "if nh < -1e300 {", "a singleton row does not lower the upper bound"),
    ("if rhi < 1e299 {\n                        nl = rhi / lasta;", "if rhi < 1e299 {\n                        nl = rlo / lasta;", "a singleton row with a negative coefficient takes the wrong side"),
    ("if lo - hi > 1e-9 * (1.0 + mag(lo) + mag(hi)) {\n                        return 1;", "if false {\n                        return 1;", "crossing bounds from a singleton row are not infeasible"),
    ("if rlo > tol(rlo) || rhi < 0.0 - tol(rhi) {", "if false {", "(equivalent) an empty row is not checked; the two activity tests, which run first on the same row, refuse it (design.md 22.14)"),
    ("if hi <= lo {", "if hi < lo - 1.0 {", "a fixed column is not substituted"),
    ("var canlow = rf[o_cost + j] >= 0.0;", "var canlow = true;", "a column is lowered whatever its cost"),
    ("var canhigh = rf[o_cost + j] <= 0.0;", "var canhigh = true;", "a column is raised whatever its cost"),
    ("if a > 0.0 {\n                            if rf[o_rlo + i] > -1e299 {\n                                canlow = false;", "if a > 0.0 {\n                            if false {\n                                canlow = false;", "a lower side does not block lowering a column with a positive coefficient"),
    ("if rf[o_rhi + i] < 1e299 {\n                                canhigh = false;\n                            }\n                        } else if a < 0.0 {", "if false {\n                                canhigh = false;\n                            }\n                        } else if a < 0.0 {", "an upper side does not block raising a column with a positive coefficient"),
    ("if rf[o_rhi + i] < 1e299 {\n                                canlow = false;", "if false {\n                                canlow = false;", "an upper side does not block lowering a column with a negative coefficient"),
    ("if rf[o_rlo + i] > -1e299 {\n                                canhigh = false;\n                            }\n                        }", "if false {\n                                canhigh = false;\n                            }\n                        }", "a lower side does not block raising a column with a negative coefficient"),
    ("rf[o_rlo + i] = rf[o_rlo + i] - a * v;", "rf[o_rlo + i] = rf[o_rlo + i] + a * v;", "a substituted column moves the lower side the wrong way"),
    ("rf[o_rhi + i] = rf[o_rhi + i] - a * v;", "rf[o_rhi + i] = rf[o_rhi + i] + a * v;", "a substituted column moves the upper side the wrong way"),
    ("} else if canhigh {\n                    remove_column(ri, rf, j, hi);", "} else if canhigh {\n                    remove_column(ri, rf, j, lo);", "a column that may be raised is fixed at its lower bound"),
    ("qf[q_clo + nj] = rf[o_clo + j];", "qf[q_clo + nj] = rf[o_chi + j];", "the reduced problem takes the upper bound as the lower"),
    ("qf[q_rlo + ni] = rf[o_rlo + i];", "qf[q_rlo + ni] = rf[o_rhi + i];", "the reduced problem takes the upper side of a row as the lower"),
    ("qf[q_cost + nj] = rf[o_cost + j];", "qf[q_cost + nj] = 0.0;", "the reduced problem loses the costs"),
    ("while ri[29] == 1 && sweeps < 20 {", "while ri[29] == 1 && sweeps < 1 {", "one sweep only"),
    ("ri[24] = ri[24] + 1;\n                ri[29] = 1;\n            } else if cnt == 1", "ri[24] = ri[24] + 1;\n            } else if cnt == 1", "(equivalent) an empty row does not count as a change; the removal of its last live column set the flag already (design.md 22.14)"),
    ("ri[25] = ri[25] + 1;\n    return 0;", "return 0;", "the removed columns are not counted"),
    ("sign = -1.0;", "sign = 1.0;", "a maximisation is minimised"),
    ("rf[o_rhi + i] = rhs;\n        } else if s == 1 {", "rf[o_rhi + i] = rhs + 1.0;\n        } else if s == 1 {", "a <= row has the wrong right side"),
    ("rf[o_rlo + i] = rhs;\n            rf[o_rhi + i] = 1e300;", "rf[o_rlo + i] = rhs + 1.0;\n            rf[o_rhi + i] = 1e300;", "a >= row has the wrong right side"),
    ("rf[o_cost + ints[l.obj_col(t)]] = sign * fl[l.obj_coef(t)];", "rf[o_cost + ints[l.obj_col(t)]] = fl[l.obj_coef(t)];", "the sense of a maximisation is not applied to the costs"),
]

killed = survived = invalid = 0
only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = os.environ.get("PYTHON", sys.executable)
for n, (old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "tests", "scripts"):
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
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), SOLVE_METHOD="sparse")   # check_presolve.py does not use SOLVE_METHOD for its own runs
        dead = False
        for gate in ("check_presolve.py", "check_highs.py", "check_dense_vs_sparse.py"):
            try:
                rc = subprocess.run([py, os.path.join(tmp, "scripts", gate)], cwd=tmp, env=env, capture_output=True, timeout=900).returncode
            except subprocess.TimeoutExpired:
                rc = 1
            if rc != 0:
                dead = True
                break
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}" + (f" [{gate}]" if dead else ""), flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
