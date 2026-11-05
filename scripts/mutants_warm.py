#!/usr/bin/env python3
"""Mutants of the warm start of the cut rounds (ws_load_warm in lib/lp/revised.cho and lp_round / mir_rounds in lib/mip/mip.cho, docs/design.md 22.3), judged by scripts/check_warm.py. Each mutant is
built in a scratch copy of the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md (22.3). Needs CANCHO=the compiler.
Usage: CANCHO=... python3 scripts/mutants_warm.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
R = "lib/lp/revised.cho"
M = "lib/mip/mip.cho"
MUTANTS = [
    # the copy of the old state
    (R, "        wi[wi[9] + c] = owi[owi[9] + c];\n", "", "the position of each column is not copied"),
    (R, "        wi[wi[10] + c] = owi[owi[10] + c];\n", "", "the side of each nonbasic column is not copied"),
    (R, "        wf[wi[18] + c] = owf[owi[18] + c];\n", "", "the nonbasic values are not copied"),
    (R, "    while c < n + mo {", "    while c < n {", "the old logicals are not copied"),
    (R, "        wi[wi[8] + i] = owi[owi[8] + i];\n", "", "the old basis is not copied"),
    (R, "        wf[wi[21] + i] = owf[owi[21] + i];\n", "", "the dual steepest-edge weights are not copied"),
    (R, "    while i < mo {\n        wi[wi[8] + i]", "    while i < mo - 1 {\n        wi[wi[8] + i]", "the basis of the last old row is not copied"),
    (R, "    wi[32] = 0;\n    return refactor(wi, wf, fi, ff);\n}\n\n// The dual simplex from the current state.", "    wi[32] = 0;\n    return 0;\n}\n\n// The dual simplex from the current state.", "the warm state is not factorised"),
    # the rounds
    (M, "let usewarm = warm_on && have && !retry;", "let usewarm = false;", "every round is solved cold"),
    (M, "let usewarm = warm_on && have && !retry;", "let usewarm = warm_on && !retry;", "the first round is warm too, from the empty state"),
    (M, "                                    have = okc;\n", "                                    have = true;\n", "a round after a failed LP starts warm"),
    (M, "                                    if usewarm {\n                                        stats[80] = stats[80] + 1;\n                                    }\n", "", "the warm solves are not counted"),
    (M, "if cc != sx.s_optimal() || mag(xcv[n] - xv[n]) > 1e-7 * (1.0 + mag(xv[n])) {", "if cc != sx.s_optimal() {", "the self-check does not compare the values"),
    (M, "        code = le.run(1, w, wi, fi, ff, st, m, n, 1000000000);", "        code = le.run(1, w, wi, fi, ff, st, m, n, 10);", "an LP of the rounds is stopped after 10 iterations"),
    (M, "        x[n] = objective_at(ints, fl, w, o_v);\n        fres[1] = sense_sign(ints) * x[n];", "        x[n] = 0.0;\n        fres[1] = 0.0;", "the value of the LP is not reported"),
    (M, "                                        } else if round + 1 >= 300 || stall >= 150 {", "                                        } else if false {", "the last LP after the round limit is not solved"),
    (M, "                                            if usewarm {\n                                                // no cut at this vertex", "                                            if false {\n                                                // no cut at this vertex", "a round that finds no cut at a warm vertex ends the rounds (no cold retry)"),
    (M, "                                                stats[83] = stats[83] + 1;\n", "", "the cold retries are not counted"),
    (M, "                                    stats[79] = stats[79] + stv[0];", "", "the iterations of the rounds are not counted"),
    (M, "                                        stats[82] = stats[82] + stv[0];\n", "", "the iterations of the cold solves are not counted"),
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
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"))
        dead = subprocess.run([py, os.path.join(tmp, "scripts/check_warm.py")], cwd=tmp, env=env, capture_output=True, timeout=1200).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
