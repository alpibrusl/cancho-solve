#!/usr/bin/env python3
"""Mutants of the model generator `lab gen ev` (tools/lab/main.cho, docs/design.md 22.18), judged by scripts/check_lab.py. Each mutant is built in a scratch copy of the repository and is killed when the
gate fails; one that builds and passes is a survivor and must be explained in design.md. Needs CANCHO=the compiler.
Usage: CANCHO=... python3 scripts/mutants_lab.py   (ONLY=3,4 to run some)"""
import os, shutil, subprocess, sys, tempfile

CANCHO = os.environ["CANCHO"]
L = "tools/lab/main.cho"
MUTANTS = [
    (L, "    y = y ^ (y >> 11);\n", "    y = y ^ (y >> 12);\n", "tempering: the first shift is 12"),
    (L, "    y = y ^ ((y << 7) & 0x9d2c5680);\n", "    y = y ^ ((y << 7) & 0x9d2c5681);\n", "(equivalent) tempering: bit 0 of the first mask, which y << 7 never has set"),
    (L, "    let a = next32(mt) >> 5;\n", "    let a = next32(mt) >> 6;\n", "random(): 26 bits of the high word"),
    (L, "    while r >= n {\n", "    while r > n {\n", "randbelow accepts n itself"),
    (L, "    var r = next32(mt) >> (32 - k);\n    while", "    var r = next32(mt) >> (31 - k);\n    while", "randbelow takes one bit too many"),
    (L, "            key = (n >> 32) & mask32();\n", "            key = 0;\n", "the second limb of the seed is zero"),
    (L, "    mt[0] = 0x80000000;\n    mt[624] = 624;\n    return 0;\n}\n\nfn twist", "    mt[624] = 624;\n    return 0;\n}\n\nfn twist", "init_by_array leaves mt[0] as it is"),
    (L, "        mt[i] = ((mt[i] ^ ((p ^ (p >> 30)) * 1566083941)) - i) & mask32();\n", "        mt[i] = ((mt[i] ^ ((p ^ (p >> 30)) * 1566083941)) - i + 1) & mask32();\n", "the second pass of init_by_array is off by one"),
    (L, "    if kf % 2 == 0 {\n        return kf;\n    }\n    return kf + 1;\n}\n\n// A price", "    return kf + 1;\n}\n\n// A price", "price: a tie goes up, not to even"),
    (L, "    if diff < 0.0 {\n        return kf;\n    }\n", "", "price: a value below its tie goes up"),
    (L, "    let err = ((ah * bh - p) + ah * bl + al * bh) + al * bl;\n", "    let err = 0.0;\n", "price: the product error is dropped, a tie of 100 x is decided on the rounded product"),
    (L, "    if f % 2 == 0 {\n        return f;\n    }\n    return f + 1;\n}\n\n// Python's `round(x, 2)`", "    return f + 1;\n}\n\n// Python's `round(x, 2)`", "round(): a tie goes up, not to even"),
    (L, "    let grid = round_even(5.5 * float_of(v));\n", "    let grid = round_even(5.0 * float_of(v));\n", "the grid limit is 5 V"),
    (L, "                chargers = v / 2;\n", "                chargers = v / 3;\n", "a third of the vehicles in chargers"),
    (L, "                if d > t {\n                    d = t;\n                }\n", "", "(equivalent) the departure is not clamped to T: a + T/3 + T/2 < T, so min(d, T) never changes d"),
    (L, "                if d < a + t / 2 {\n", "                if d < a + t / 3 {\n", "the shortest window is a third of T"),
    (L, "                if nd < 1 {\n                    nd = 1;\n                }\n", "                if nd < 0 {\n                    nd = 0;\n                }\n", "(equivalent) a need may be zero: u >= 0.25 and d - a >= T/2 >= 1 make the need at least 3"),
    (L, "if vv[p] <= c && c < vv[v + p] {", "if vv[p] <= c && c <= vv[v + p] {", "a vehicle is plugged in in its departure slot"),
    (L, "    var third = t / 3;\n", "    var third = t / 2;\n", "the arrival window is half of T"),
    (L, "let u = 0.25 + 0.25 * random53(mt);", "let u = 0.25 + 0.2 * random53(mt);", "uniform(0.25, 0.5) with the wrong span"),
    (L, "if v >= 1 && v <= 1000 && t >= 2 &&", "if v >= 1 && v <= 1000 && t >= 1 &&", "T = 1 is accepted"),
    (L, "seed * 1000003 + v * 101 + t", "seed * 1000003 + v * 101", "the seed does not include T"),
]

only = [int(k) for k in os.environ.get("ONLY", "").split(",") if k]
py = sys.executable
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
        b = subprocess.run([CANCHO, "build", "--bin", "lab"], capture_output=True, text=True, cwd=tmp)
        if b.returncode != 0:
            print(f"INVALID mutant {n} ({what}): does not build: {(b.stderr or b.stdout).strip()[:200]}")
            invalid += 1
            continue
        env = dict(os.environ, LAB=os.path.join(tmp, "build/lab"))
        dead = subprocess.run([py, os.path.join(tmp, "scripts", "check_lab.py")], cwd=tmp, env=env, capture_output=True, timeout=1800).returncode != 0
        equivalent = what.startswith("(equivalent)")
        print(("killed  " if dead else "explained" if equivalent else "SURVIVED") + f" {n}: {what}", flush=True)
        killed += dead
        survived += (not dead) and not equivalent

print(f"mutants: {killed} killed, {survived} survived, {invalid} invalid")
sys.exit(1 if survived or invalid else 0)
