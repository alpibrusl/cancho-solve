#!/usr/bin/env python3
"""Deliberate changes to the checker (docs/CLAUDE.md: mutants are all killed, or each survivor explained). Each mutant is built in a scratch copy and the three gates run
against it; a mutant is killed when a gate fails. Needs CANCHO=the compiler. Usage: CANCHO=... python3 scripts/mutants.py"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
SRC = ["lib/model/layout.cho", "lib/model/lex.cho", "lib/model/expr.cho", "lib/model/stmt.cho", "lib/lp/simplex.cho", "lib/lp/sparse.cho", "lib/lp/revised.cho", "lib/mip/lpeng.cho", "lib/mip/mip.cho", "lib/verify/verify.cho", "tools/solve/emit.cho", "tools/solve/main.cho"]

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
    ("lib/lp/simplex.cho", "if rk < rbest - 1e-12 ||", "if rk > rbest + 1e-12 ||", "the entering column has the largest ratio"),
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
    # the long step (design.md section 17)
    ("lib/lp/simplex.cho", "w[o_v + cj] = nbound;", "w[o_v + cj] = w[o_v + cj];", "a passed column keeps its value"),
    ("lib/lp/simplex.cho", "wi[p_at + cj] = now;", "wi[p_at + cj] = wi[p_at + cj];", "a passed column keeps its bound marker"),
    ("lib/lp/simplex.cho", "let slope = delta - mag(w[rb + cj]) * (w[o_h + cj] - w[o_l + cj]);", "let slope = delta;", "a passed column does not lower the slope"),
    ("lib/lp/simplex.cho", "delta = slope;", "delta = delta + 0.0;", "the slope is not carried to the next column"),
    ("lib/lp/simplex.cho", "w[o_v + wi[i]] = w[o_v + wi[i]] - w[i * big + cj] * dx;", "w[o_v + wi[i]] = w[o_v + wi[i]] + w[i * big + cj] * dx;", "the basic values take a flip with the wrong sign"),
    ("lib/lp/simplex.cho", "if slope <= 1e-9 * (1.0 + worst) {", "if slope <= 0.5 * (1.0 + worst) {", "a loose slope tolerance enters too early"),
    # the steepest-edge pricing (design.md section 17.2); only gate 5 can see these
    ("lib/lp/simplex.cho", "let sc = viol * viol / w[o_w + i];", "let sc = viol / w[o_w + i];", "the violation is not squared in the price"),
    ("lib/lp/simplex.cho", "let sc = viol * viol / w[o_w + i];", "let sc = viol * viol;", "the price ignores the weights"),
    ("lib/lp/simplex.cho", "w[o_w + i] = si;", "w[o_w + i] = w[o_w + i];", "a rewritten row keeps its old weight"),
    ("lib/lp/simplex.cho", "w[o_w + r] = sr;", "w[o_w + r] = 1.0;", "the pivot row's weight is not taken from the row"),
    ("lib/lp/simplex.cho", "si = si + nv * nv;", "si = si + nv;", "the weight sums values, not squares"),
    # branch and bound (design.md section 19); gate 6 (check_mip.py) has to kill these
    ("lib/mip/mip.cho", "let dist = fmin(f, 1.0 - f);", "let dist = fmax(f, 1.0 - f);", "an integral column is branched on"),
    ("lib/mip/mip.cho", "return z >= inc - 1e-9 * (1.0 + mag(inc));", "return z > inc - 1e-9 * (1.0 + mag(inc));", "a node as good as the incumbent is not cut"),
    ("lib/mip/mip.cho", "return z > inc - 1.0 + 1e-6;", "return z > inc - 2.0 + 1e-6;", "the whole-objective cut is off by one and cuts improving nodes"),
    ("lib/mip/mip.cho", "if inc_have && !(z < mf[o_inc] - 1e-9 * (1.0 + mag(mf[o_inc]))) {", "if inc_have && !(z > mf[o_inc] - 1e-9 * (1.0 + mag(mf[o_inc]))) {", "the incumbent is replaced by a worse point"),
    ("lib/mip/mip.cho", "mf[o_tx + j] = fround(w[o_v + j]);", "mf[o_tx + j] = w[o_v + j];", "integer columns are not rounded"),
    ("lib/mip/mip.cho", "mf[o_hi + idn] = fv;", "mf[o_hi + idn] = mf[o_bh + jb];", "the down child does not tighten its bound"),
    ("lib/mip/mip.cho", "mf[o_lo + idu] = fv + 1.0;", "mf[o_lo + idu] = fv;", "the up child's bound is one too low"),
    ("lib/mip/mip.cho", "le.refresh(w, wi, m, n);\n                        var lim = dcap;", "var lim = dcap;", "the basic values are not refreshed after a bound change"),
    ("lib/mip/mip.cho", "v = mi[o_par + v];", "v = 0;", "restoring applies only the last change of the path"),
    ("lib/mip/mip.cho", "if b < best {\n            best = b;", "if b > best {\n            best = b;", "the best bound is the largest open bound"),
    ("lib/mip/mip.cho", "bmode, 1e-6);\n                if jb < 0 {", "bmode, 0.3);\n                if jb < 0 {", "a loose integrality tolerance"),
    ("lib/mip/mip.cho", "} else if nodes >= nl {", "} else if nodes > nl {", "the node limit allows one more node"),
    ("lib/mip/mip.cho", "if v - fv < 0.5 {", "if v - fv > 0.5 {", "the plunge goes to the far child"),
    ("lib/mip/mip.cho", "if bk < ba || bk == ba && mi[o_open + k] < mi[o_open + at] {", "if bk > ba || bk == ba && mi[o_open + k] < mi[o_open + at] {", "best-bound selection takes the worst bound"),
    ("lib/mip/mip.cho", "var at = cnt - 1;", "var at = 0;", "depth-first takes the oldest open node"),
    ("lib/mip/mip.cho", "if !rows_ok(ints, fl, mf, o_tx, 1e-7) {\n        return false;", "if !rows_ok(ints, fl, mf, o_tx, 1.0) {\n        return false;", "a rounded point is accepted with violated rows"),
    ("lib/mip/mip.cho", "if s == 2 && mag(act - rhs) > sc {", "if s == 2 && mag(act - rhs) > 1e9 {", "an equality row is not checked on a rounded point"),
    ("lib/mip/mip.cho", "le.copy_f(w, rw);", "le.copy_f(rw, w);", "restoring overwrites the root tableau"),
    ("lib/mip/mip.cho", "if mf[o_bl + cc] > mf[o_bh + cc] {\n                            empty = true;", "if mf[o_bl + cc] >= mf[o_bh + cc] {\n                            empty = true;", "a fixed column makes the node infeasible"),
    ("lib/mip/mip.cho", "if opts[0] >= 0 && remaining <= 0 {\n            reason = 2;\n            running = false;\n            extra = -1e300;", "if opts[0] >= 0 && remaining < 0 {\n            reason = 2;\n            running = false;\n            extra = -1e300;", "the iteration budget allows one more LP"),
    ("lib/mip/mip.cho", "fres[0] = sign * inc;", "fres[0] = inc;", "a maximisation prints its objective with the wrong sign"),
    ("lib/mip/mip.cho", "if !prunable(mf[o_bd + id], have, inc, whole) {\n            found = id;", "if true {\n            found = id;", "open nodes are not cut when taken"),
    ("lib/mip/mip.cho", "mf[o_psd + cc] = mf[o_psd + cc] + dl;", "mf[o_psd + cc] = mf[o_psd + cc];", "the down pseudo-cost is not updated"),
    ("lib/mip/mip.cho", "score = fmax(ed * f, 1e-6) * fmax(eu * (1.0 - f), 1e-6);", "score = fmax(ed * f, 1e-6) + fmax(eu * (1.0 - f), 1e-6);", "the pseudo-cost score is a sum"),
    ("lib/mip/lpeng.cho", "w[o_v + j] = lo;\n        } else {\n            w[o_v + j] = hi;", "w[o_v + j] = hi;\n        } else {\n            w[o_v + j] = lo;", "a nonbasic column moves to the wrong side after a bound change"),
    ("lib/mip/lpeng.cho", "w[o_v + wi[i]] = -s;", "w[o_v + wi[i]] = s;", "refresh has the wrong sign"),
    ("tools/solve/emit.cho", "w = json.put_bool(heap, w, worst <= 1e-6);", "w = json.put_bool(heap, w, true);", "verified is always true (MIP)"),
    # the sparse engine of the search (docs/design.md 19.6); mutants whose `what` starts with "[sparse]" are judged by the gates run with the sparse engine
    ("lib/lp/revised.cho", "    if wi[wi[9] + j] < 0 {\n        if wi[wi[10] + j] == 0 {\n            wf[wi[18] + j] = lo;", "    if wi[wi[9] + j] < 0 {\n        if wi[wi[10] + j] == 1 {\n            wf[wi[18] + j] = lo;", "[sparse] a nonbasic column moves to the bound of the wrong side"),
    ("lib/lp/revised.cho", "    wf[wi[20] + j] = hi;\n    if wi[wi[9] + j] < 0 {", "    wf[wi[20] + j] = lo;\n    if wi[wi[9] + j] < 0 {", "[sparse] the upper bound is not set"),
    ("lib/lp/revised.cho", "    wf[wi[19] + j] = lo;\n    wf[wi[20] + j] = hi;", "    wf[wi[19] + j] = hi;\n    wf[wi[20] + j] = hi;", "[sparse] the lower bound is not set"),
    ("lib/lp/revised.cho", "    if wi[32] == 1 {\n        let m = wi[0];", "    if wi[32] == 7 {\n        let m = wi[0];", "[sparse] a copied state is not refactorised"),
    ("lib/lp/revised.cho", "    wi[32] = 1;\n    return 0;", "    wi[32] = 0;\n    return 0;", "[sparse] copied is not remembered"),
    ("lib/mip/lpeng.cho", "        return rv.ws_mark_copied(wi);", "        return 0;", "[sparse] the engine is not told the state was copied"),
    ("lib/mip/mip.cho", "                        le.copied(eng, wi);\n", "", "[sparse] the search does not tell the engine the state was copied"),
    ("lib/lp/revised.cho", "    return wi[18];\n}", "    return wi[19];\n}", "[sparse] the values are read at the lower bounds"),
    ("lib/lp/revised.cho", "    return 8 * (nnz + m) + 4096;", "    return 1;", "[sparse] the pool of the factorisation is empty"),
    ("lib/lp/revised.cho", "    return ws_pool(m, nnz) > 16000000;", "    return ws_pool(m, nnz) > 16;", "[sparse] every model is too large"),
    ("lib/mip/lpeng.cho", "        return rv.wf_len(m, n, nnz);", "        return rv.wf_len(m, n, 1);", "[sparse] the float state is too short"),
    ("lib/mip/lpeng.cho", "        return rv.ws_set_bounds(wi, w, j, lo, hi);", "        return 0;", "[sparse] a bound change is ignored"),
    ("lib/mip/lpeng.cho", "        return rv.ws_refresh(wi, w, fi, ff);", "        return 0;", "[sparse] the values are not refreshed"),
    ("lib/mip/mip.cho", "                        st = le.refresh(eng, w, wi, fi, ff, m, n);", "                        st = 0;\n                        le.refresh(eng, w, wi, fi, ff, m, n);", "[sparse] a failed refresh is ignored"),
    ("lib/mip/mip.cho", "            if eng == 0 {\n                st = 0;\n            }", "            st = 0;", "[sparse] a failed load of the root is ignored"),
    ("lib/mip/mip.cho", "    if reason == 4 {\n        stats[0] = iters;", "    if reason == 7 {\n        stats[0] = iters;", "[sparse] numerical trouble is reported as a result"),
    ("tools/solve/main.cho", "eng = auto_method(n);", "eng = 0;", "[sparse] auto never chooses the sparse engine"),
    ("tools/solve/main.cho", "                    sv[8] = eng;\n", "", "[sparse] the report does not say which engine ran"),
    ("tools/solve/emit.cho", "    if stats[8] == 1 {\n        w = json.put_string(heap, w, \"sparse\");", "    if stats[8] == 0 {\n        w = json.put_string(heap, w, \"sparse\");", "[sparse] the report names the wrong engine"),
    ("lib/mip/mip.cho", "            if st > sx.s_limit() {\n                reason = 4;\n                running = false;\n                extra = -1e300;\n            } else if st == sx.s_limit() {", "            if st > 77 {\n                reason = 4;\n                running = false;\n                extra = -1e300;\n            } else if st == sx.s_limit() {", "[sparse] numerical trouble at the root is read as a limit"),

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
        sparse = what.startswith("[sparse]")
        env = dict(os.environ, SOLVE=out, SOLVE_METHOD="sparse" if sparse else "dense")  # these mutants are of the dense solver (the default `auto` would send sparse models elsewhere)
        dead = False
        for gate in (("check_mip_engines.py", "check_mip.py", "check_nodes.py", "check_cli.py") if sparse else ("check_language.py", "check_expand.py", "check_highs.py", "check_mip.py", "check_nodes.py", "check_cli.py", "check_iterations.py")):
            if subprocess.run([sys.executable, os.path.join(tmp, "scripts", gate)], cwd=tmp, env=env, capture_output=True).returncode != 0:
                dead = True
                break
        print(("killed  " if dead else "SURVIVED") + f" {n}: {what}")
        killed += dead
        survived += not dead

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
