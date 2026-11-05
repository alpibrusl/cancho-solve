#!/usr/bin/env python3
"""Mutants of the verifier (lib/verify/verify.cho, docs/design.md section 20.5), judged by scripts/check_verify.py. Each mutant is built in a scratch copy of the repository and is
killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md. Needs CANCHO=the compiler and scipy (for the gate).
Usage: CANCHO=... python3 scripts/mutants_verify.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
F = "lib/verify/verify.cho"
MUTANTS = [
    # bounds
    ("if !(dl <= tol * sl) {", "if !(dl <= 1.0 + tol * sl) {", "the lower bound is not checked (a whole unit of slack)"),
    ("} else if !(dh <= tol * sh) {", "} else if !(dh <= 1.0 + tol * sh) {", "the upper bound is not checked"),
    ("if !(dl <= tol * sl) {", "if !(dl < tol * sl) {", "a bound violation of exactly the limit is refused (strictness)"),
    ("let dl = fin(lo - v);", "let dl = fin(v - lo);", "the lower-bound violation has the wrong sign"),
    ("let dh = fin(v - hi);", "let dh = fin(hi - v);", "the upper-bound violation has the wrong sign"),
    ("let sl = 1.0 + mag(lo);", "let sl = 1.0;", "the lower bound's scale is dropped"),
    ("let sh = 1.0 + mag(hi);", "let sh = 1.0;", "the upper bound's scale is dropped"),
    ("let sl = 1.0 + mag(lo);", "let sl = 1000.0 + mag(lo);", "the lower bound's scale is 1000"),
    ("if dl / sl > mx[0] {", "if dl / sl < mx[0] {", "the largest bound violation is the smallest"),
    ("if dh / sh > mx[0] {", "if dh / sh < mx[0] {", "the largest upper-bound violation is the smallest"),
    # integrality
    ("if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] < 2 {", "if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] < 1 {", "int variables are not checked for integrality (only bool)"),
    ("if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] < 2 {", "if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] < 3 {", "real variables are checked for integrality"),
    ("if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] < 2 {", "if ints[l.sym_class(k)] == 1 && ints[l.sym_kind(k)] == 1 {", "bool variables are not checked for integrality"),
    ("if !(f <= tol) {", "if !(f <= 0.4) {", "a loose integrality tolerance"),
    ("if 1.0 - f < f {\n        f = 1.0 - f;\n    }", "", "the distance to the next whole number above is ignored"),
    ("let t = float_of(truncate(v));", "let t = float_of(truncate(v)) + 1.0;", "the distance is measured from the wrong whole number"),
    ("if mag(v) >= 4.0e15 {\n        return 0.0;\n    }", "if mag(v) >= 0.5 {\n        return 0.0;\n    }", "values of magnitude half and up count as whole"),
    ("if f > mx[1] {", "if f < mx[1] {", "the largest integrality violation is the smallest"),
    # rows
    ("var d = act - rhs;\n            if ints[l.row_sense(r)] == 1 {", "var d = act - rhs;\n            if ints[l.row_sense(r)] == 7 {", "a >= row is checked as <="),
    ("} else if ints[l.row_sense(r)] == 2 {\n                d = mag(act - rhs);", "} else if ints[l.row_sense(r)] == 7 {\n                d = mag(act - rhs);", "an equality row is checked as <= (only one side)"),
    ("d = rhs - act;", "d = act - rhs;", "a >= row has the wrong direction"),
    ("d = mag(act - rhs);", "d = act - rhs;", "an equality is one-sided"),
    ("let scale = fin(1.0 + bigger(mag(rhs), fin(terms)));", "let scale = fin(1.0 + mag(rhs));", "the row scale ignores the size of the terms"),
    ("let scale = fin(1.0 + bigger(mag(rhs), fin(terms)));", "let scale = fin(1.0 + terms + mag(rhs));", "the row scale is the sum of the terms and the right side (too loose)"),
    ("let scale = fin(1.0 + bigger(mag(rhs), fin(terms)));", "let scale = 1.0;", "the row scale is one"),
    ("let scale = fin(1.0 + bigger(mag(rhs), fin(terms)));", "let scale = fin(1.0 + bigger(mag(rhs), fin(terms))) * 1000.0;", "the row tolerance is 1000 times too loose"),
    ("if !(d <= tol * scale) {\n                let nm = row_name", "if !(d < tol * scale) {\n                let nm = row_name", "a row violation of exactly the limit is refused"),
    ("let prod = fl[l.term_coef(t2)] * xv[ints[l.term_col(t2)]];", "let prod = fl[l.term_coef(t2)] * xv[ints[l.term_col(t2)]] + 0.0 * xv[0];", "(equivalent) a zero term is added to the row activity"),
    ("let act = sv[0] + sv[1];", "let act = sv[0];", "the compensation of the row sum is dropped"),
    ("while t2 < ints[l.row_start(r + 1)] {", "while t2 < ints[l.row_start(r + 1)] - 1 {", "the last term of each row is skipped"),
    ("while r < ints[l.h_ncons()] {\n            sv[0] = 0.0;", "while r < ints[l.h_ncons()] - 1 {\n            sv[0] = 0.0;", "the last row is skipped"),
    ("if d / scale > mx[2] {", "if d / scale < mx[2] {", "the largest row violation is the smallest"),
    # the objective
    ("if has_claim {\n        let dd", "if false {\n        let dd", "the claimed objective is never compared"),
    ("let dd = fin(mag(claimed - ev[0]));", "let dd = fin(claimed - ev[0]);", "an objective claimed too high is not noticed"),
    ("let dd = fin(mag(claimed - ev[0]));", "let dd = fin(ev[0] - claimed);", "an objective claimed too low is not noticed"),
    ("let lim = tol * (1.0 + mag(fin(ev[0])));", "let lim = tol * (1.0 + 1000.0 * mag(fin(ev[0])));", "the objective tolerance scales with 1000 times the value"),
    ("let lim = tol * (1.0 + mag(fin(ev[0])));", "let lim = tol;", "the objective tolerance is absolute"),
    ("add_to(sv, fl[l.obj_const(0)]);", "add_to(sv, 0.0);", "the objective's constant is dropped"),
    ("add_to(sv, fl[l.obj_coef(t3)] * xv[ints[l.obj_col(t3)]]);", "add_to(sv, fl[l.obj_coef(t3)]);", "the objective ignores x"),
    ("while t3 < ints[l.h_obj_nnz()] {", "while t3 < ints[l.h_obj_nnz()] - 1 {", "the last objective term is skipped"),
    ("if ints[l.h_sense()] != 0 {\n            add_to", "if ints[l.h_sense()] == 7 {\n            add_to", "the objective is never evaluated (0)"),
    # reading the solution
    ("hit[v] = 1;", "hit[v] = 0;", "used members are not marked (every key looks unknown)"),
    ("if json.count(tape, xo) > ints[l.h_nvars()] {", "if json.count(tape, xo) > ints[l.h_nvars()] + 1000000 {", "unknown variables are not looked for"),
    ("if repeated {", "if !repeated {", "a repeated name and an unknown one are swapped"),
    ("status = refuse_named(heap, io, 6, buffer.bytes(nb));", "status = refuse_named(heap, io, 7, buffer.bytes(nb));", "a missing variable is reported as unknown"),
    ("if xval - xval != 0.0 {", "if xval - xval != 7.0 {", "a non-finite value is accepted"),
    ("xv[ints[l.sym_base(k)] + off] = xval;", "xv[ints[l.sym_base(k)] + off] = 0.0;", "every value is read as zero"),
    ("} else if !json.is_number(tape, v) {", "} else if false {", "a value that is not a number is accepted"),
    ("v = json.get(src, tape, xo, buffer.bytes(nb));", "v = 0 - 1;", "an unordered key is not found (reported missing)"),
    ("} else if co >= 0 && !json.is_number(tp, co) {", "} else if false {", "a claimed objective that is not a number is accepted"),
    ("if claimed - claimed != 0.0 {", "if claimed - claimed != 7.0 {", "a non-finite claimed objective is accepted"),
    ("co >= 0, claimed, tol,", "false, claimed, tol,", "the claimed objective is never passed on"),
    ("if acc[0] < 10 {", "if acc[0] < 0 {", "no violation is listed"),
    ("if acc[0] == 0 {\n        acc[1] = code;", "if acc[0] == 99 {\n        acc[1] = code;", "the tag of the first violation is never set"),
    ("if acc[0] > 0 {\n        var m", "if acc[0] > 1 {\n        var m", "a single violation is not a refusal"),
    # the report
    ("w = json.put_float(heap, w, tol);\n    w = json.put_key(heap, w, \"max_bound_violation\");", "w = json.put_float(heap, w, 1.0e-6);\n    w = json.put_key(heap, w, \"max_bound_violation\");", "the tolerance printed is always the default"),
    ("w = json.put_bool(heap, w, checked);", "w = json.put_bool(heap, w, true);", "objective_checked is always true"),
    ("w = json.put_float(heap, w, mx[2] + 0.0);", "w = json.put_float(heap, w, 0.0);", "max_row_violation is always 0"),
    # the tolerance flag
    ("if v >= 0.0 && v <= 0.1 {", "if v >= 0.0 && v <= 100.0 {", "a tolerance above 0.1 is accepted"),
    ("if v >= 0.0 && v <= 0.1 {", "if v > 0.0 && v <= 0.1 {", "a tolerance of zero is refused"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
killed = survived = invalid = 0
for n, (old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts", "tests"):
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
        dead = subprocess.run([py, os.path.join(tmp, "scripts/check_verify.py")], cwd=tmp, env=env, capture_output=True, timeout=600).returncode != 0
        equivalent = what.startswith("(equivalent)")   # explained in design.md 20.6: it cannot change any output
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
