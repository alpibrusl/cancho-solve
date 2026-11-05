#!/usr/bin/env python3
"""Mutants of the revised dual simplex (lib/lp/revised.cho, docs/design.md section 18.3.2), judged by the gates that run it: check_highs.py and check_iterations.py with
SOLVE_METHOD=sparse, check_dense_vs_sparse.py, check_cli.py (only the `run` part matters). Each mutant is built in a scratch copy; killed when a gate fails. Kept apart from
scripts/mutants.py. Needs CANCHO=the compiler. Usage: CANCHO=... python3 scripts/mutants_revised.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
F = "lib/lp/revised.cho"
MUTANTS = [
    ("ok = atb == 0 && av < 0.0 || atb == 1 && av > 0.0;", "ok = atb == 0 && av > 0.0 || atb == 1 && av < 0.0;", "the wrong direction is eligible when a basic variable is too low"),
    ("let dq = -(target - wf[o_z + leaving]) / piv;", "let dq = (target - wf[o_z + leaving]) / piv;", "the entering variable moves the wrong way"),
    ("wf[o_dd + j] = wf[o_dd + j] - fd * wf[o_ar + j];", "wf[o_dd + j] = wf[o_dd + j] + fd * wf[o_ar + j];", "a structural reduced cost takes the update with the wrong sign"),
    ("wf[o_dd + j] = wf[o_dd + j] + fd * wf[o_rho + s - nt];", "wf[o_dd + j] = wf[o_dd + j] - fd * wf[o_rho + s - nt];", "a logical reduced cost takes the update with the wrong sign"),
    ("wf[o_dd + leaving] = -fd;", "wf[o_dd + leaving] = fd;", "the leaving variable gets the wrong reduced cost"),
    ("if fd != 0.0 {", "if fd == 7.0 {", "the reduced costs are not updated"),
    ("wf[o_z + wi[o_bs + i]] = wf[o_z + wi[o_bs + i]] - wf[o_sv + i];", "wf[o_z + wi[o_bs + i]] = wf[o_z + wi[o_bs + i]] + wf[o_sv + i];", "the basic values take the flips with the wrong sign"),
    ("wf[o_sv + cj - n] = wf[o_sv + cj - n] - dx;", "wf[o_sv + cj - n] = wf[o_sv + cj - n] + dx;", "a flipped logical enters the flip vector with the wrong sign"),
    ("wf[o_sv + wi[o_cr + t]] = wf[o_sv + wi[o_cr + t]] + wf[o_cv + t] * dx;", "wf[o_sv + wi[o_cr + t]] = wf[o_sv + wi[o_cr + t]] + dx;", "a flipped structural ignores its coefficients"),
    ("var nw = wf[o_wt + i] - 2.0 * kap * wf[o_tau + i] + kap * kap * wr;", "var nw = wf[o_wt + i] + 2.0 * kap * wf[o_tau + i] + kap * kap * wr;", "the weight update has the wrong sign on the cross term"),
    ("var nw = wf[o_wt + i] - 2.0 * kap * wf[o_tau + i] + kap * kap * wr;", "var nw = wf[o_wt + i] - 2.0 * kap * wf[o_tau + i];", "the weight update drops the last term"),
    ("wf[o_wt + r] = wr / (piv * piv);", "wf[o_wt + r] = wr;", "the pivot row's weight is not scaled"),
    ("wf[o_wt + r] = wr;\n            // the pivot row", "wf[o_wt + r] = wf[o_wt + r];\n            // the pivot row", "the pivot row's weight is not refreshed from rho"),
    ("if nw < 1e-4 {\n                                nw = 1e-4;", "if nw < 0.0 {\n                                nw = 1e-4;", "the weight floor is gone"),
    ("let sc = viol * viol / wf[o_wt + i];", "let sc = viol / wf[o_wt + i];", "the violation is not squared in the price"),
    ("let sc = viol * viol / wf[o_wt + i];", "let sc = viol * viol;", "the price ignores the weights"),
    ("let full = sp.push_eta(fi, ff, r, wf[o_al..o_al + m]);", "let full = 0;", "the basis change is not recorded as an eta"),
    ("wf[o_z + wi[o_bs + p]] = -wf[o_sv + p];", "wf[o_z + wi[o_bs + p]] = wf[o_sv + p];", "the basic values are recomputed with the wrong sign"),
    ("dj = dj - wf[o_rho + wi[o_cr + t]] * wf[o_cv + t];", "dj = dj + wf[o_rho + wi[o_cr + t]] * wf[o_cv + t];", "the duals are recomputed with the wrong sign"),
    ("dj = wf[o_rho + j - n];", "dj = -wf[o_rho + j - n];", "a logical's recomputed reduced cost has the wrong sign"),
    ("sign = -1.0;", "sign = 1.0;", "a maximisation is minimised"),
    ("wf[o_hi + n + i] = rhs;\n        } else if s == 1 {", "wf[o_hi + n + i] = rhs + 1.0;\n        } else if s == 1 {", "a <= row has the wrong right side"),
    ("wf[o_lo + n + i] = rhs;\n            wf[o_hi + n + i] = 1e300;", "wf[o_lo + n + i] = rhs + 1.0;\n            wf[o_hi + n + i] = 1e300;", "a >= row has the wrong right side"),
    ("if q < 0 {\n                result = s_infeasible();", "if q < 0 {\n                result = s_optimal();", "no entering column is called optimal"),
    ("} else if iter >= limit {", "} else if iter > limit {", "the iteration limit allows one more"),
    ("wf[o_ar + cj] = wf[o_ar + cj] + ri * wf[o_rv + t];", "wf[o_ar + cj] = wf[o_ar + cj] + ri;", "the pivot row ignores the coefficients"),
    ("av = -wf[o_rho + s - nt];", "av = wf[o_rho + s - nt];", "a logical's entry in the pivot row has the wrong sign"),
    ("wf[o_bv + at] = -1.0;", "wf[o_bv + at] = 1.0;", "the logical's basis column has the wrong sign"),
    ("wf[o_al + q - n] = -1.0;", "wf[o_al + q - n] = 1.0;", "the entering logical's column has the wrong sign"),
    ("if slope <= 1e-9 * (1.0 + worst) {", "if slope <= 0.5 * (1.0 + worst) {", "a loose slope tolerance enters too early"),
    ("let slope = delta - acj * (wf[o_hi + cj] - wf[o_lo + cj]);", "let slope = delta;", "a passed column does not lower the slope"),
    ("wf[o_z + cj] = nbound;", "wf[o_z + cj] = wf[o_z + cj];", "a passed column keeps its value"),
    ("if rk < rbest - 1e-12 || rk <= rbest + 1e-12 && (ak > ab || ak == ab && jk < jb) {", "if rk > rbest + 1e-12 || rk <= rbest + 1e-12 && (ak > ab || ak == ab && jk < jb) {", "the entering column has the largest ratio"),
    ("if fi[4] > 0 {\n                let code = refactor(wi, wf, fi, ff);", "if fi[4] > 100000 {\n                let code = refactor(wi, wf, fi, ff);", "optimal is declared without a refactorisation"),
    ("if fi[4] > 0 && (mag(piv - arq) > 1e-7 * (1.0 + mag(arq)) || mag(piv) < 1e-9) {", "if fi[4] > 100000 && (mag(piv - arq) > 1e-7 * (1.0 + mag(arq)) || mag(piv) < 1e-9) {", "a pivot disagreement is ignored"),
    ("if full != 0 || fi[4] >= interval() {", "if full != 0 {", "no refactorisation at the interval"),
    ("fn interval() -> [] int {\n    return 64;", "fn interval() -> [] int {\n    return 1;", "a refactorisation at every iteration"),
    ("if dj >= -tol {\n                        dj = 0.0;", "if dj >= -1e9 {\n                        dj = 0.0;", "a recomputed dual infeasibility is always clamped"),
    ("var cap = limit;\n    if limit < 0 {\n        cap = 100 * big + 1000;", "var cap = limit;\n    if limit < 0 {\n        cap = 3;", "the default iteration limit is tiny"),
    ("if wf[o_c + j] >= 0.0 {\n            wi[o_at + j] = 0;", "if wf[o_c + j] <= 0.0 {\n            wi[o_at + j] = 0;", "variables start at the bound their cost avoids"),
    ("wi[o_cr + at] = i;\n            wf[o_cv + at] = wf[o_rv + t];", "wi[o_cr + at] = 0;\n            wf[o_cv + at] = wf[o_rv + t];", "the column form puts every entry in row 0"),
]

def build(root):
    return subprocess.run([CANCHO, "build", "--bin", "solve"], capture_output=True, text=True, cwd=root)

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
        b = build(tmp)
        if b.returncode != 0:
            print(f"INVALID mutant {n} ({what}): does not build: {(b.stderr or b.stdout).strip()[:200]}")
            invalid += 1
            continue
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), SOLVE_METHOD="sparse")
        dead = False
        for gate in ("check_highs.py", "check_iterations.py", "check_dense_vs_sparse.py"):
            try:
                rc = subprocess.run([py, os.path.join(tmp, "scripts", gate)], cwd=tmp, env=env, capture_output=True, timeout=900).returncode
            except subprocess.TimeoutExpired:
                rc = 1
            if rc != 0:
                dead = True
                break
        print(("killed  " if dead else "SURVIVED") + f" {n}: {what} [{gate}]" if dead else f"SURVIVED {n}: {what}", flush=True)
        killed += dead
        survived += not dead

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
