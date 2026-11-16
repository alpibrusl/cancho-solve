#!/usr/bin/env python3
"""Mutants of the named experiments (tools/solve/exper.cho and the `--exp` option of tools/solve/main.cho, docs/design.md 22.18), judged by scripts/check_exp.py. Each mutant is built in a scratch copy of
the repository and is killed when the gate fails; one that builds and passes is a survivor and must be explained in design.md. Needs CANCHO=the compiler and build/lab.
Usage: CANCHO=... python3 scripts/mutants_exp.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
E = "tools/solve/exper.cho"
M = "tools/solve/main.cho"
MUTANTS = [
    (E, "        return 128;\n", "        return 256;\n", "profile names the wrong bit"),
    (E, "        return 134217728;\n", "        return 67108864;\n", "restarts names the wrong bit"),
    (E, "        return 65536;\n", "        return 32768;\n", "aging names the wrong bit"),
    (E, "pub fn offset_of(k: int) -> [] int {\n    if k == 0 {", "pub fn offset_of(k: int) -> [] int {\n    if k == 17 {\n        return 0;\n    }\n    if k == 0 {", "restarts=N is N, not N + 1 restarts"),
    (E, "pub fn max_of(k: int) -> [] int {\n    if k == 0 {", "pub fn max_of(k: int) -> [] int {\n    if k == 17 {\n        return 15;\n    }\n    if k == 0 {", "restarts allows 15"),
    (E, "            if which < 0 || (seen / pow2(which)) % 2 == 1 {\n", "            if which < 0 {\n", "a name may be repeated"),
    (E, "                if eq >= 0 {\n                    return 0 - 1;\n                }\n                bits = bits + bit_of(which);\n", "                bits = bits + bit_of(which);\n", "a flag may take a value"),
    (E, "                if eq < 0 {\n                    return 0 - 1;\n                }\n                let v", "                if eq < 0 {\n                    return bits + bit_of(which);\n                }\n                let v", "a field may go without its value"),
    (E, "                if v < min_of(which) || v > max_of(which) {\n", "                if v > max_of(which) {\n", "a field may be below its minimum"),
    (E, "                if v < min_of(which) || v > max_of(which) {\n", "                if v < min_of(which) || v > max_of(which) + 1 {\n", "a field may be one above its maximum"),
    (E, "    if len(text) == 0 {\n        return 0 - 1;\n    }\n    var bits = 0;", "    if len(text) == 0 {\n        return 0;\n    }\n    var bits = 0;", "an empty list is no experiment"),
    (E, "        out = json.put_int(heap, out, offset_of(k));\n", "        out = json.put_int(heap, out, 0);\n", "introspect does not say the offset"),
    (M, "                    if good && !(named && raw) {\n", "                    if good {\n", "--exp and --experiment may be given together"),
    (M, "&& !named && exper.parse", "&& exper.parse", "--exp may be given twice"),
    (E, "                bits = bits + bit_of(which) * (v + offset_of(which));\n", "                bits = bit_of(which) * (v + offset_of(which));\n", "a field drops the bits before it"),
    (E, "    if (seen / pow2(20)) % 2 == 1 && (seen / pow2(19)) % 2 == 0 {\n        return 0 - 1;\n    }\n", "", "gomory-nnz is accepted without gomory"),
    (E, "        return 4294967296;\n", "        return 2147483648;\n", "gomory-nnz names the bit of gomory"),
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
        env = dict(os.environ, SOLVE=os.path.join(tmp, "build/solve"), LAB=lab)
        dead = subprocess.run([py, os.path.join(tmp, "scripts", "check_exp.py")], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
