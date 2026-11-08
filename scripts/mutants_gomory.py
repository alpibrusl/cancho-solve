#!/usr/bin/env python3
"""Mutants of the Gomory cuts (lib/mip/gomory.cho and cmir.pool_push, docs/design.md 22.18), judged by scripts/check_gomory.py with QUICK=1 (the small models). Each mutant is built in a scratch copy of
the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md. Needs CANCHO=the compiler and build/lab.
Usage: CANCHO=... python3 scripts/mutants_gomory.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
G = "lib/mip/gomory.cho"
P = "lib/mip/cmir.cho"
MUTANTS = [
    (G, "                        sg = cj;\n", "                        sg = 0.0 - cj;\n", "the upper-bound substitution has the sign of the lower"),
    (G, "                    aj = 0.0 - abar;\n", "                    aj = abar;\n", "a column at its upper bound keeps the sign of abar"),
    (G, "    let f0 = beta - ffloor(beta);\n    var rhs", "    let f0 = 1.0 - (beta - ffloor(beta));\n    var rhs", "f0 is 1 minus the fraction"),
    (G, "                abar = 0.0 - v[j - n];\n", "                abar = v[j - n];\n", "a logical column is +I, not -I"),
    (G, "                            cj = fj / f0;\n", "                            cj = fj / (1.0 - f0);\n", "an integer column with f_j <= f0 is divided by 1 - f0"),
    (G, "                            cj = (1.0 - fj) / (1.0 - f0);\n", "                            cj = (1.0 - fj) / f0;\n", "an integer column with f_j > f0 is divided by f0"),
    (G, "                        cj = aj / f0;\n", "                        cj = aj / (1.0 - f0);\n", "a continuous column with a_j > 0 is divided by 1 - f0"),
    (G, "                        cj = (0.0 - aj) / (1.0 - f0);\n", "                        cj = (0.0 - aj) / f0;\n", "a continuous column with a_j < 0 is divided by f0"),
    (G, "                        rhs = rhs + sg * bnd;\n", "                        rhs = rhs - sg * bnd;\n", "the bound goes to the right side with the wrong sign"),
    (G, "    var rhs = 0.0 - 1.0;\n", "    var rhs = 0.0 - 0.5;\n", "(equivalent for validity) the cut asks for half: sum c t >= 1/2 is implied by the cut, a weaker one, and the gate judges validity"),
    (G, "                    if j < n && si[j] == 1 && mag(bnd - ffloor(bnd + 0.5)) < 1e-9 {\n", "                    if si[j % n] == 1 && mag(bnd - ffloor(bnd + 0.5)) < 1e-9 {\n", "a logical is taken as the integer column j mod n"),
    (G, "                    if j < n && si[j] == 1 && mag(bnd - ffloor(bnd + 0.5)) < 1e-9 {\n", "                    if j < n && mag(bnd - ffloor(bnd + 0.5)) < 1e-9 {\n", "every structural column is taken as integer"),
    (G, "                    if j < n && si[j] == 1 && mag(bnd - ffloor(bnd + 0.5)) < 1e-9 {\n", "                    if j < n && si[j] == 1 {\n", "(equivalent) an integer column's bound is not tested for being an integer: the models of the gate have integer bounds"),
    (G, "    sp.btran(fi, ff, v);\n", "", "rho is e_r, not e_r B^-1"),
    (G, "                if f0 >= 0.01 && f0 <= 0.99 {\n", "                if f0 >= 0.0 && f0 <= 1.0 {\n", "(equivalent) rows with an integral basic value are tried: f0 near 0 gives coefficients the pool refuses (dynamism, efficacy)"),
    (G, "            if mag(abar) >= 1e-9 && hi - lo >= 1e-9 {\n", "            if mag(abar) >= 1e-9 {\n", "(equivalent) a fixed column is not dropped: its t_j is 0 and a term on it only restates that"),
    (G, "                            var t = ints[l.row_start(j - n)];\n", "                            var t = ints[l.row_start(j - n)] + 1;\n", "a logical's row loses its first term"),
    (P, "    sf[o_prhs(n, mcap) + npool] = rhs;\n", "    sf[o_prhs(n, mcap) + npool] = rhs - 0.5;\n", "the pool's right side is made stronger"),
    (P, "        let cv = g[goff + j];\n", "        let cv = g[j];\n", "the cut is read from the start of the work slice"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
lab = os.path.abspath("build/lab")
killed = survived = invalid = 0
for n, (F, old, new, what) in enumerate(MUTANTS):
    if only and n not in only:
        continue
    with tempfile.TemporaryDirectory() as tmp:
        for d in ("lib", "tools", "scripts"):
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
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), LAB=lab, QUICK="1")
        dead = subprocess.run([py, os.path.join(tmp, "scripts", "check_gomory.py")], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
