#!/usr/bin/env python3
"""Deliberate changes to the checker (docs/CLAUDE.md: mutants are all killed, or each survivor explained). Each mutant is built in a scratch copy and the three gates run
against it; a mutant is killed when a gate fails. Needs CANCHO=the compiler. Usage: CANCHO=... python3 scripts/mutants.py"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
SRC = ["lib/model/layout.cho", "lib/model/lex.cho", "lib/model/expr.cho", "lib/model/stmt.cho", "lib/lp/simplex.cho", "tools/solve/emit.cho", "tools/solve/main.cho"]

# (file, old, new, what it breaks)
MUTANTS = [
    ("lib/model/expr.cho", "expression(text, ints, fl, mult * prod);", "expression(text, ints, fl, mult);", "a group's numeric factor is dropped"),
    ("lib/model/expr.cho", "term(text, ints, fl, 0.0 - mult);", "term(text, ints, fl, mult);", "subtraction adds"),
    ("lib/model/stmt.cho", "fl[l.row_rhs(row)] = 0.0 - rest + 0.0;", "fl[l.row_rhs(row)] = rest;", "the right side keeps the wrong sign"),
    ("lib/model/expr.cho", "if i < 0 || i >= ints[l.sym_n0(k)] {", "if i < 0 || i > ints[l.sym_n0(k)] {", "an index one past the end is accepted"),
    ("lib/model/stmt.cho", "} else if c == '>' {\n            sense = 1;", "} else if c == '>' {\n            sense = 0;", "a >= is stored as <="),
    ("lib/model/expr.cho", "while i < stop && !lx.failed(ints) {", "while i <= stop && !lx.failed(ints) {", "a sum runs one step too far"),
    ("tools/solve/emit.cho", "off % ints[l.sym_n1(k)]", "off / ints[l.sym_n1(k)]", "the second index of a 2-D name"),
    ("lib/model/expr.cho", "prod / x;", "prod * x;", "a division multiplies"),
    ("lib/model/stmt.cho", "|| lo > hi {", "|| lo >= hi {", "equal bounds are refused"),
    ("lib/model/stmt.cho", "|| hi <= lo {", "|| hi < lo {", "an empty range is accepted"),
    ("lib/model/expr.cho", "ints[l.sym_class(k)] == 1 {\n                return true;", "ints[l.sym_class(k)] == 2 {\n                return true;", "a group with a variable counts as a number"),
    ("lib/model/expr.cho", "ints[l.touched(j - gap)] > t {", "ints[l.touched(j - gap)] < t {", "terms come out in decreasing order"),
    ("lib/model/stmt.cho", "ints[l.h_pos()] = body_end;\n    return 0;\n}\n\n// Reads", "return 0;\n}\n\n// Reads", "a forall does not step past its body"),
    ("lib/model/expr.cho", "ints[l.h_pos()] = body_end;\n    return 0;", "return 0;", "a sum does not step past its body"),
    ("lib/model/expr.cho", "} else if ints[l.h_numeric()] == 1 {\n                    lx.fail(ints, lx.r_not_constant(), at);", "} else if ints[l.h_numeric()] == 7 {\n                    lx.fail(ints, lx.r_not_constant(), at);", "a variable in a range is accepted"),
    ("lib/model/expr.cho", "if x == 0.0 {", "if x == 1.0 {", "division by zero is not noticed"),
    ("lib/model/stmt.cho", "if kind == 1 && (!ex.whole(lo) || !ex.whole(hi)) {", "if kind == 7 && (!ex.whole(lo) || !ex.whole(hi)) {", "a fractional integer bound is accepted"),
    ("lib/model/expr.cho", "ints[l.h_steps()] > 10000000", "ints[l.h_steps()] > 100000000000", "the loop budget is lifted"),
    # the simplex (S2); gate 4 (check_highs.py) and the limit test of gate 3 have to kill these
    ("lib/lp/simplex.cho", "ratio < best - 1e-12 ||", "ratio > best + 1e-12 ||", "the entering column has the largest ratio"),
    ("lib/lp/simplex.cho", "ok = at == 0 && a < 0.0 || at == 1 && a > 0.0;", "ok = at == 0 && a > 0.0 || at == 1 && a < 0.0;", "the wrong direction is eligible when a basic variable is too low"),
    ("lib/lp/simplex.cho", "let dq = -(target - w[o_v + leaving]) / piv;", "let dq = (target - w[o_v + leaving]) / piv;", "the entering variable moves the wrong way"),
    ("lib/lp/simplex.cho", "if fd != 0.0 {", "if fd == 7.0 {", "the reduced costs are not updated"),
    ("lib/lp/simplex.cho", "if q < 0 {\n            return s_infeasible();", "if q < 0 {\n            return s_optimal();", "no entering column is called optimal"),
    ("lib/lp/simplex.cho", "if w[o_d + j] >= 0.0 {\n            wi[p_at + j] = 0;", "if w[o_d + j] <= 0.0 {\n            wi[p_at + j] = 0;", "variables start at the bound their cost avoids"),
    ("lib/lp/simplex.cho", "sign = -1.0;", "sign = 1.0;", "a maximisation is minimised"),
    ("lib/lp/simplex.cho", "} else {\n            w[o_l + n + i] = rhs;\n            w[o_h + n + i] = rhs;", "} else {\n            w[o_l + n + i] = rhs;\n            w[o_h + n + i] = rhs + 1.0;", "an equality row is a range"),
    ("lib/lp/simplex.cho", "w[o_h + n + i] = rhs;\n        } else if s == 1 {", "w[o_h + n + i] = rhs + 1.0;\n        } else if s == 1 {", "a <= row has the wrong right side"),
    ("lib/lp/simplex.cho", "w[o_v + leaving] = target;", "w[o_v + leaving] = target + 1.0;", "the leaving variable is not put at its bound"),
    ("lib/lp/simplex.cho", "if iter >= limit {", "if iter > limit {", "the iteration limit allows one more"),
    ("lib/lp/simplex.cho", "v < lb - 1e-9 * (1.0 + mag(lb))", "v < lb - 1e-1 * (1.0 + mag(lb))", "a loose primal tolerance accepts violated rows"),
    ("lib/lp/simplex.cho", "if i != r {\n                w[o_v + wi[i]]", "if i == r {\n                w[o_v + wi[i]]", "the other basic values are not updated"),
    ("lib/lp/simplex.cho", "w[i * big + ints[l.term_col(t)]] = -fl[l.term_coef(t)];", "w[i * big + ints[l.term_col(t)]] = fl[l.term_coef(t)];", "the sign of the constraint matrix"),
    ("tools/solve/emit.cho", "obj = obj + fl[l.obj_coef(t2)] * x[ints[l.obj_col(t2)]];", "obj = obj + fl[l.obj_coef(t2)];", "the reported objective ignores x"),
    ("tools/solve/emit.cho", "w = json.put_bool(heap, w, viol <= 1e-6);", "w = json.put_bool(heap, w, true);", "verified is always true"),
]

def build(root, out):
    files = [os.path.join(root, f) for f in SRC]
    return subprocess.run([CANCHO, "build", *files, "--std", "-o", out], capture_output=True, text=True, cwd=root)

killed = survived = invalid = 0
only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
for n, (path, old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "tests", "scripts"):
            shutil.copytree(d, os.path.join(tmp, d))
        f = os.path.join(tmp, path)
        text = open(f).read()
        if old not in text:
            print(f"INVALID mutant {n} ({what}): the text to change is not in {path}")
            invalid += 1
            continue
        open(f, "w").write(text.replace(old, new, 1))
        out = os.path.join(tmp, "solve")
        b = build(tmp, out)
        if b.returncode != 0:
            print(f"INVALID mutant {n} ({what}): does not build: {b.stderr.strip()[:200]}")
            invalid += 1
            continue
        env = dict(os.environ, SOLVE=out)
        dead = False
        for gate in ("check_language.py", "check_expand.py", "check_highs.py", "check_cli.py"):
            if subprocess.run([sys.executable, os.path.join(tmp, "scripts", gate)], cwd=tmp, env=env, capture_output=True).returncode != 0:
                dead = True
                break
        print(("killed  " if dead else "SURVIVED") + f" {n}: {what}")
        killed += dead
        survived += not dead

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
