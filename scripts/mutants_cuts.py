#!/usr/bin/env python3
"""Mutants of the implied cuts (lib/mip/cuts.cho, docs/design.md section 19.8), judged by scripts/check_cuts.py. Each mutant is built in a scratch copy of the repository and is
killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md (19.8). Needs CANCHO=the compiler and scipy (for the gate).
Usage: CANCHO=... python3 scripts/mutants_cuts.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
F = "lib/mip/cuts.cho"
MUTANTS = [
    # recognising a variable upper bound
    ("p > 0.0 && q > 0.0 && sf[y] >= 0.0 {", "p > 0.0 && sf[y] >= 0.0 {", "a row with a positive coefficient on y counts as a variable upper bound"),
    ("p > 0.0 && q > 0.0 && sf[y] >= 0.0 {", "p > 0.0 && q > 0.0 {", "a variable upper bound on an integer column that may be negative"),
    ("let c = q / p;", "let c = p / q;", "the ratio of the variable upper bound is inverted"),
    ("if si[n + x] < 0 || c < sf[2 * n + x] {", "if si[n + x] < 0 || c > sf[2 * n + x] {", "the loosest variable upper bound is kept"),
    ("mag(fl[l.row_rhs(r)]) < 1e-12 {", "mag(fl[l.row_rhs(r)]) < 1e12 {", "a row with a right side counts as a variable upper bound"),
    ("            if sense == 1 {\n                sg = 0.0 - 1.0;\n            }\n            let j1", "            let j1", "a >= variable-upper-bound row is not negated"),
    # reading a row as a covering row
    ("            if sense == 0 {\n                sg = 0.0 - 1.0;\n            }\n            var b", "            if sense == 1 {\n                sg = 0.0 - 1.0;\n            }\n            var b", "a <= row is read as a >= row without negation"),
    ("                        b = b - a * sf[n + j];", "                        b = b + a * sf[n + j];", "a continuous column without a bound lowers the right side the wrong way"),
    ("                        b = b - a * sf[j];\n                    }\n                }\n                if target", "                        b = b + a * sf[j];\n                    }\n                }\n                if target", "a negative term raises the right side the wrong way"),
    ("                    } else if sf[n + j] > 1e20 {\n                        ok = false;", "                    } else if sf[n + j] > 1e30 {\n                        ok = false;", "(equivalent) a continuous column with an infinite upper bound is used; the language refuses an unbounded variable (solve.unbounded-domain), so none exists"),
    ("                        if sf[j] < 0.0 {\n                            ok = false;", "                        if sf[j] < -5.0 {\n                            ok = false;", "an integer column with a negative lower bound is used"),
    ("                        w = a * sf[2 * n + j];\n                        used = true;", "                        w = a;\n                        used = true;", "the weight of a variable upper bound ignores its ratio"),
    ("                        w = a * sf[2 * n + j];\n                        used = true;", "                        w = a * sf[2 * n + j];", "a row without a variable upper bound is used too"),
    ("if ok && used && nt >= 2 && b > 1e-9 {", "if ok && used && nt >= 1 && b > 1e-9 {", "a row over one integer column gets a cut"),
    # the cut
    ("let rhs = fceil(b / dv - 1e-9);", "let rhs = ffloor(b / dv - 1e-9);", "the right side is rounded down"),
    ("fl2[l.term_coef(nnz + i)] = fceil(sf[3 * n + j] / dv - 1e-9);", "fl2[l.term_coef(nnz + i)] = ffloor(sf[3 * n + j] / dv - 1e-9);", "the coefficients are rounded down"),
    ("let added = put_cut(ints2, fl2, si, sf, n, nt, wmax, b, m + cuts, nnz);", "let added = put_cut(ints2, fl2, si, sf, n, nt, wmin, b, m + cuts, nnz);", "the first cut divides by the smallest weight"),
    ("if wmin < wmax - 1e-9 && cuts < cap {", "if false {", "the second cut is never added"),
    ("    if cap > 4096 {\n        cap = 4096;\n    }", "    if cap > 4 {\n        cap = 4;\n    }", "at most four cuts are added"),
    ("                si[3 * n + jj] = 0;\n", "", "the marks of a row are left for the next row"),
    ("    ints2[l.h_ncons()] = m + cuts;\n", "", "the cuts are not counted among the rows"),
    ("    ints2[l.h_nnz()] = nnz;\n", "", "(equivalent) the header's nonzero count is not updated; no engine reads it"),
    ("if rhs < 1.0 || row + 1 > l.maxrows() || nnz + nt > l.maxnz() {", "if rhs < 0.0 || row + 1 > l.maxrows() || nnz + nt > l.maxnz() {", "(equivalent) a cut with a zero right side is kept; the clamp rounds it away from the gate's instances"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
killed = survived = invalid = 0
for n, (old, new, what) in enumerate(MUTANTS):
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
        dead = subprocess.run([py, os.path.join(tmp, "scripts/check_cuts.py")], cwd=tmp, env=env, capture_output=True, timeout=1200).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
