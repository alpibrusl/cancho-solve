#!/usr/bin/env python3
"""Mutants of the MIR cuts (lib/mip/cmir.cho) and of the rounds and the RINS driver around them (lib/mip/mip.cho), docs/design.md 21.2, judged by scripts/check_mir.py. Each mutant is built in a
scratch copy of the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md (21.3). Needs CANCHO=the compiler and scipy.
Usage: CANCHO=... python3 scripts/mutants_cmir.py   (ONLY=3,4 to run some; JOBS=4 runs that many at once)"""
import concurrent.futures, os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
C = "lib/mip/cmir.cho"
M = "lib/mip/mip.cho"
MUTANTS = [
    # the MIR inequality
    (C, "let rb = ffloor(bq + 1e-9);\n                let f0 = bq - rb;", "let rb = ffloor(bq + 1e-9) + 1.0;\n                let f0 = bq - rb + 1.0;", "the right side is rounded up"),
    (C, "if f0 >= 0.05 && f0 <= 0.95 {", "if f0 >= 0.0 && f0 <= 1.0 {", "(equivalent in practice) no safety margin on the fractional part: f0 within 1e-9 of 0 or 1 does not occur on the gate's instances"),
    (C, "let cy = fl2 + fj / (1.0 - f0);\n                        var ylen", "let cy = fl2 + fj / f0;\n                        var ylen", "the fractional coefficient is divided by f0 instead of 1 - f0"),
    (C, "                        var fj = aj - fl2;\n                        fj = fj - f0;", "                        var fj = aj - fl2;", "the fractional part is not reduced by f0"),
    (C, "let cv = sf[5 * n + j] / (d * (1.0 - f0));\n                        var sv", "let cv = sf[5 * n + j] / (d * f0);\n                        var sv", "a continuous column is divided by f0 instead of 1 - f0"),
    (C, "if ok && cs < 0.0 {", "if ok && cs > 0.0 {", "the continuous columns with a positive coefficient are kept and the negative ones dropped"),
    (C, "                    rhs2 = rhs2 - a * sf[j];\n                    cs = a;", "                    rhs2 = rhs2 + a * sf[j];\n                    cs = a;", "a lower bound is subtracted with the wrong sign"),
    (C, "                    rhs2 = rhs2 - a * sf[n + j];\n                    cs = 0.0 - a;", "                    rhs2 = rhs2 - a * sf[n + j];\n                    cs = a;", "an upper bound substitution keeps the sign of the coefficient"),
    (C, "sf[4 * n + y] = sf[4 * n + y] + a * sf[2 * n + j];", "sf[4 * n + y] = sf[4 * n + y] + a;", "the ratio of the variable upper bound is ignored"),
    (C, "if kind == 1 {\n                    rhs2 = rhs2 - a * sf[j];", "if kind == 9 {\n                    rhs2 = rhs2 - a * sf[j];", "a continuous column never takes its lower bound"),
    (C, "                if si[n + j] >= 0 {\n                    let v = sf[2 * n + j] * x[si[n + j]] - x[j];\n                    if v < best {\n                        best = v;\n                        kind = 3;", "                if false {\n                    let v = sf[2 * n + j] * x[si[n + j]] - x[j];\n                    if v < best {\n                        best = v;\n                        kind = 3;", "variable upper bounds are never used in a cut"),
    (C, "if finite(sf[n + j]) && sf[n + j] - x[j] < best {\n                    best = sf[n + j] - x[j];\n                    kind = 2;", "if finite(sf[n + j]) && sf[n + j] - x[j] < best - 1e30 {\n                    best = sf[n + j] - x[j];\n                    kind = 2;", "a continuous column never takes its upper bound"),
    (C, "            } else if finite(hi) && x[y] > 0.5 * (lo + hi) {\n                comp = true;", "            } else if finite(hi) && x[y] > 2.0 * hi {\n                comp = true;", "an integer column is never complemented"),
    (C, "                rhs2 = rhs2 - a * hi;\n                sf[4 * n + y] = 0.0 - a;", "                rhs2 = rhs2 - a * lo;\n                sf[4 * n + y] = 0.0 - a;", "a complemented column subtracts its lower bound"),
    (C, "if (finite(lo) && lo != ffloor(lo)) || (finite(hi) && hi != ffloor(hi)) || (!finite(lo) && !finite(hi)) {", "if (!finite(lo) && !finite(hi)) {", "an integer column with a fractional bound is used"),
    (C, "if viol > 1e-5 && sq > 1e-18 {", "if viol > -1e9 && sq > 1e-18 {", "a cut that is not violated is kept"),
    (C, "let viol = lhs - rh;\n    if !ok", "let viol = lhs - rh + 1.0;\n    if !ok", "(equivalent in effect) the violation is overstated by one in the final test: the cuts of the gate's instances are violated by more than the pool needs"),
    # emitting the cut
    (C, "            rh = rh - cy * sf[n + y];\n            sf[6 * n + y] = sf[6 * n + y] - cy;", "            rh = rh - cy * sf[y];\n            sf[6 * n + y] = sf[6 * n + y] - cy;", "a complemented column puts its lower bound in the right side"),
    (C, "            sf[6 * n + j] = sf[6 * n + j] - cv;\n            rh = rh - cv * sf[n + j];", "            sf[6 * n + j] = sf[6 * n + j] + cv;\n            rh = rh - cv * sf[n + j];", "an upper-bound continuous column has the wrong sign in the cut"),
    (C, "sf[6 * n + y] = sf[6 * n + y] + cv * sf[2 * n + j];", "sf[6 * n + y] = sf[6 * n + y] + cv;", "the ratio is dropped from the cut"),
    (C, "cmax > 1e6 * cmin", "cmax > 1e60 * cmin", "(equivalent in practice) no limit on the dynamism of a cut: none of the gate's instances has one beyond 1e6"),
    (C, "at - start >= 400", "at - start >= 4", "a cut of more than four terms is refused"),
    # aggregation
    (C, "if eff * sf[3 * n + bj] < 0.0 && row_slack(ints, fl, sf, n, k, sg2) <= tolk {", "if eff * sf[3 * n + bj] > 0.0 && row_slack(ints, fl, sf, n, k, sg2) <= tolk {", "a row with the same sign on the column is added (the column doubles instead of cancelling)"),
    (C, "if eff * sf[3 * n + bj] < 0.0 && row_slack(ints, fl, sf, n, k, sg2) <= tolk {", "if eff * sf[3 * n + bj] < 0.0 {", "a row that is not tight is aggregated"),
    (C, "let mult = (0.0 - sf[3 * n + bj]) / pc2;", "let mult = sf[3 * n + bj] / pc2;", "the multiplier of the aggregated row has the wrong sign"),
    (C, "bg = bg + mult * fs2 * fl[l.row_rhs(pick)];", "bg = bg + mult * fs2;", "the right side of the aggregated row is not added"),
    (C, "sf[3 * n + bj] = 0.0;\n                                bg", "bg", "(equivalent) the cancelled column is not set to zero: it is zero up to rounding"),
    (C, "while attempt < 9 && !done {", "while attempt < 1 && !done {", "no aggregation: single rows only"),
    (C, "                var fsg = 1.0;\n                if sg < 0 {\n                    fsg = 0.0 - 1.0;\n                }", "                var fsg = 1.0;\n                if sg < 0 {\n                    fsg = 1.0;\n                }", "a row used with the minus sign is not negated"),
    (C, "if sg > 0 && s != 1 {\n        return rhs - act;\n    }", "if sg > 0 && s != 1 {\n        return act - rhs;\n    }", "the slack of a <= row has the wrong sign"),
    (C, "var sg = 1;\n            if osg == 1 {\n                sg = 0 - 1;\n            }\n            osg = osg + 1;", "var sg = 1;\n            osg = osg + 1;", "(equivalent in practice) the minus orientation of rows is never a start: the gate's cuts also start from the plus one"),
    (C, "&& has_fractional(ints, si, sf, x, n, r) {", "&& false {", "no row is a start"),
    # the pool and the rows
    (C, "ints2[l.row_sense(m)] = 0;\n    fl2[l.row_rhs(m)] = sf[o_prhs(n, mcap) + k];", "ints2[l.row_sense(m)] = 1;\n    fl2[l.row_rhs(m)] = sf[o_prhs(n, mcap) + k];", "a cut is appended as a >= row"),
    (C, "if rhs - act <= 1e-6 * (1.0 + mag(rhs)) {", "if true {", "(equivalent) the cuts that are not tight are kept: the answer is the same, the LPs are larger"),
    (C, "if rhs - act <= 1e-6 * (1.0 + mag(rhs)) {", "if act - rhs <= 1e-6 * (1.0 + mag(rhs)) {", "the cut rows that are kept are the ones that are slack"),
    (C, "    ints2[l.h_ncons()] = w;\n    ints2[l.h_nnz()] = nnz;\n    return w - m0;", "    return w - m0;", "the purge does not shorten the model"),
    (C, "if sf[pe + k] > be {", "if sf[pe + k] < be {", "the least efficacious cut is taken first"),
    (C, "            if dot * dot > 0.81 * na * nb {", "            if dot * dot > 1.81 * na * nb {", "(equivalent in effect) parallel cuts are never skipped: a weaker selection, the same answers"),
    (C, "            if dot * dot > 0.81 * na * nb {", "            if dot * dot > 0.0 * na * nb {", "every cut after the first is skipped as parallel"),
    (C, "        sf[pe + best] = 0.0 - 1.0;\n        // dense copy", "        // dense copy", "a cut that was looked at is looked at again (the selection does not end)"),
    # the rounds
    (M, "taken < 300", "taken < 1", "one cut per round"),
    (M, "round < 300 && stall < 150", "round < 300 && stall < 3", "the rounds stop after three without a lift"),
    (M, "round < 300 && stall < 150", "round < 2 && stall < 150", "two rounds"),
    (M, "if round > 0 && fv[1] <= last + 1e-9 * (1.0 + mag(last)) {", "if round > 0 {", "every round after the first counts as stalled"),
    (M, "kept = cm.purge(ints2, fl2, xv, m0);", "kept = ints2[l.h_ncons()] - m0;", "the purge is skipped"),
    # the driver
    (M, "if fixed * 10 >= nint * 3 && fixed < nint {", "if fixed * 10 >= nint * 3 && fixed <= nint {", "a sub-MIP with every integer column fixed"),
    (M, "if fixed * 10 >= nint * 3 && fixed < nint {", "if fixed < nint {", "a sub-MIP around any number of fixed columns"),
    (M, "if c2 <= r_feasible() && improves(sign, fv[0], fres[0]) {", "if c2 <= r_feasible() {", "a sub-MIP's point is adopted whether it improves or not"),
    (M, "return sign * a < sign * than - 1e-9 * (1.0 + mag(than));", "return sign * a > sign * than + 1e-9 * (1.0 + mag(than));", "a worse point counts as an improvement"),
    (M, "            ctl[1] = ctl[1] * 3;", "            ctl[1] = ctl[1] + 1;", "the search pauses at every node after the first pause"),
    (M, "    var pause = 300;", "    var pause = 3;", "the first pause is at three nodes"),
    (M, "    let gcount = 6;", "    let gcount = 1;", "one LP point is kept"),
    (M, "        mf[o_inc] = inc;\n        var ji = 0;", "        var ji = 0;", "(equivalent) the incumbent value is not copied to its cell: it is read from `inc`"),
    (M, "        if have && exper / 16 % 2 == 0 {\n            rcfix = rcfix + rc_fix(eng, rw, rwi, mf, mi, m, n, o_isint, o_l0, o_h0, zroot, inc, whole);\n        }\n    } else {", "    } else {", "(equivalent in effect) reduced-cost fixing is not redone after a resume: the fixings are only an acceleration"),
    (M, "        iters = mi[o_sv + 4];", "        iters = 0;", "the iterations of a paused search are forgotten when it resumes"),
    (M, "        branched = mi[o_sv + 3];", "        branched = 0;", "(equivalent) the branched count is forgotten on a resume: it only enters the report"),
    (M, "        z = mf[o_svf];", "        z = 0.0;", "the value of the paused node is forgotten when the search resumes"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
jobs = int(os.environ.get("JOBS", "1"))
py = sys.executable


def run(n):
    f_rel, old, new, what = MUTANTS[n]
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts", "tests"):
            shutil.copytree(d, os.path.join(tmp, d))
        os.makedirs(os.path.join(tmp, "docs"))
        shutil.copytree("docs/examples", os.path.join(tmp, "docs", "examples"))
        shutil.copy("cancho.toml", tmp)
        f = os.path.join(tmp, f_rel)
        text = open(f).read()
        if old not in text:
            return n, "invalid", f"the text to change is not in {f_rel}", what
        open(f, "w").write(text.replace(old, new, 1))
        b = subprocess.run([CANCHO, "build", "--bin", "solve"], capture_output=True, text=True, cwd=tmp)
        if b.returncode != 0:
            return n, "invalid", "does not build: " + (b.stderr or b.stdout).strip()[:200], what
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), FAILFAST="1")
        try:
            dead = subprocess.run([py, os.path.join(tmp, "scripts/check_mir.py")], cwd=tmp, env=env, capture_output=True, timeout=3000).returncode != 0
        except subprocess.TimeoutExpired:
            dead = True
        return n, ("killed" if dead else ("explained" if what.startswith("(equivalent") else "SURVIVED")), "", what


todo = [n for n in range(len(MUTANTS)) if not only or n in only]
killed = survived = invalid = 0
with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
    for n, verdict, extra, what in ex.map(run, todo):
        print(f"{verdict:9s} {n}: {what} {extra}", flush=True)
        killed += verdict == "killed"
        survived += verdict == "SURVIVED"
        invalid += verdict == "invalid"
print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
