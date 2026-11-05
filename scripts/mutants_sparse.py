#!/usr/bin/env python3
"""Mutants of the sparse linear algebra (lib/lp/sparse.cho, docs/design.md section 18.3.1), judged by scripts/check_sparse.py. Kept apart from scripts/mutants.py, which
judges the model checker and the dense simplex. Each mutant is built in a scratch copy; killed when the gate fails. Needs CANCHO=the compiler, PYTHON with numpy+scipy.
Usage: CANCHO=... python3 scripts/mutants_sparse.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
MUTANTS = [
    ("fn threshold() -> [] float {\n    return 0.1;", "fn threshold() -> [] float {\n    return 0.0;", "the pivot threshold is zero (any entry may pivot)"),
    ("fn threshold() -> [] float {\n    return 0.1;", "fn threshold() -> [] float {\n    return 2.0;", "the pivot threshold is above one (nothing qualifies)"),
    ("if mag(v) > tiny() && mag(v) >= threshold() * col_max(fi, ff, jj) {", "if mag(v) > tiny() {", "a row singleton skips the threshold"),
    ("if mag(v) >= threshold() * vmax && mag(v) > tiny() {", "if mag(v) > tiny() {", "the general search skips the threshold"),
    ("x[fi[o_pc + k]] = ff[o_w1 + k];", "x[fi[o_pr + k]] = ff[o_w1 + k];", "FTRAN scatters by row instead of by position"),
    ("ff[o_w1 + k] = x[fi[o_pr + k]];", "ff[o_w1 + k] = x[fi[o_pc + k]];", "FTRAN gathers by position instead of by row"),
    ("y[fi[o_pr + k]] = ff[o_w1 + k];", "y[fi[o_pc + k]] = ff[o_w1 + k];", "BTRAN scatters by position"),
    ("ff[o_w1 + k] = y[fi[o_pc + k]];", "ff[o_w1 + k] = y[fi[o_pr + k]];", "BTRAN gathers by row"),
    ("x[fi[o_lr + e]] = x[fi[o_lr + e]] - ff[o_lv + e] * t;", "x[fi[o_lr + e]] = x[fi[o_lr + e]] + ff[o_lv + e] * t;", "FTRAN applies L with the wrong sign"),
    ("y[fi[o_pr + k]] = y[fi[o_pr + k]] - s;", "y[fi[o_pr + k]] = y[fi[o_pr + k]] + s;", "BTRAN applies L transposed with the wrong sign"),
    ("let l = ff[o_rv + t1] / pv;", "let l = ff[o_rv + t1];", "the multiplier is not divided by the pivot"),
    ("ff[o_rv + at] = 0.0 - l * ff[o_w1 + jj];", "ff[o_rv + at] = l * ff[o_w1 + jj];", "a fill-in has the wrong sign"),
    ("ff[o_rv + s2] = ff[o_rv + s2] - l * ff[o_w1 + jj];", "ff[o_rv + s2] = ff[o_rv + s2] + l * ff[o_w1 + jj];", "an updated entry has the wrong sign"),
    ("fi[o_mk + jj] = stamp;", "fi[o_mk + jj] = 0 - 1;", "an updated entry is also added as a fill-in"),
    ("                col_remove(fi, jj, p);\n", "", "the pivot row stays in the columns' patterns"),
    ("fi[o_ucr + at] = k;", "fi[o_ucr + at] = c;", "the column copy of U names the wrong row"),
    ("ff[o_ucv + at] = ff[o_uv + e2];", "ff[o_ucv + at] = 1.0;", "the column copy of U loses its values"),
    ("x[r] = t;\n        if t != 0.0 {", "if t != 0.0 {", "an eta does not scale the pivot component (FTRAN)"),
    ("let t = x[r] / ff[o_ea + n];", "let t = x[r];", "an eta does not divide by its pivot (FTRAN)"),
    ("y[r] = s / ff[o_ea + n];", "y[r] = s;", "an eta does not divide by its pivot (BTRAN)"),
    ("s = s - ff[o_ev + e] * y[fi[o_ei + e]];", "s = s + ff[o_ev + e] * y[fi[o_ei + e]];", "BTRAN applies an eta with the wrong sign"),
    ("var n = fi[4] - 1;\n    while n >= 0 {", "var n = 0;\n    while n < fi[4] {", "BTRAN applies the etas oldest first"),
    ("if j != r && mag(alpha[j]) > 1e-14 {\n            fi[fi[37] + at] = j;", "if j != r && mag(alpha[j]) > 0.5 {\n            fi[fi[37] + at] = j;", "an eta drops its smaller entries"),
    ("n = n + 1;\n    }\n    return 0;\n}\n\n// Solves y B = c.", "n = n + 2;\n    }\n    return 0;\n}\n\n// Solves y B = c.", "FTRAN skips every second eta"),
    ("if cmin == 0 {\n                return r_singular();", "if cmin == 0 {\n                return r_ok();", "an empty column is not reported as singular"),
    ("fn tiny() -> [] float {\n    return 1e-11;", "fn tiny() -> [] float {\n    return 0.5;", "a pivot below 0.5 counts as zero"),
    ("let cost = (fi[o_rl + ii] - 1) * (cmin - 1);", "let cost = 0 - (fi[o_rl + ii] - 1) * (cmin - 1);", "Markowitz picks the largest count product (more fill)"),
]

killed = survived = invalid = 0
only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = os.environ.get("PYTHON", sys.executable)
for n, (old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts"):
            shutil.copytree(d, os.path.join(tmp, d))
        shutil.copy("cancho.toml", tmp)
        f = os.path.join(tmp, "lib/lp/sparse.cho")
        text = open(f).read()
        if old not in text:
            print(f"INVALID mutant {n} ({what}): the text to change is not in sparse.cho")
            invalid += 1
            continue
        open(f, "w").write(text.replace(old, new, 1))
        b = subprocess.run([CANCHO, "build", "--bin", "sparsetest"], capture_output=True, text=True, cwd=tmp)
        if b.returncode != 0:
            print(f"INVALID mutant {n} ({what}): does not build: {(b.stderr or b.stdout).strip()[:200]}")
            invalid += 1
            continue
        env = dict(os.environ, SPARSE=os.path.join(tmp, "build/sparsetest"))
        dead = subprocess.run([py, os.path.join(tmp, "scripts/check_sparse.py")], cwd=tmp, env=env, capture_output=True, timeout=600).returncode != 0
        print(("killed  " if dead else "SURVIVED") + f" {n}: {what}")
        killed += dead
        survived += not dead

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
