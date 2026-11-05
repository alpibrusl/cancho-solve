#!/usr/bin/env python3
"""Gate 6 (docs/design.md section 18.3.1, written before lib/lp/sparse.cho): the sparse linear algebra alone. `build/sparsetest` reads a basis in column form, factorises it,
applies column replacements as product-form etas, and answers FTRAN (B x = b) and BTRAN (y B = c) for given vectors. This script builds random sparse bases, solves the same
systems with scipy's SuperLU (`splu`), and requires, for every solve: the residual of the answer against the matrix as it stands after the replacements is at most 1e-9
(scaled by 1 + |B||x|, a choice: the bases are filtered to condition number <= 1e6), and the answer agrees with SuperLU's to 1e-7 (same scaling).
The multipliers of L must stay below 1 / threshold = 10. The fill of the factorisation is judged too: nnz(L)+nnz(U) at most 1.25 times SuperLU's (COLAMD ordering; measured 0.83 to 1.0 times on the families below), and no fill at all (nnz(L)+nnz(U) at most nnz(B)) on the network-like bases; a few bases with a tiny row singleton (condition about 1e8, residual judged only) need the threshold. The hypersparse solves (design.md 21.2) are judged on vectors with one to six nonzeros: the answer must equal the dense solve's bit for bit, every nonzero must be in the returned list, no index twice;
every other eta goes in through the list form (`push_eta_h`). Families: random sparse, network-like (forests of +-1 columns plus unit columns, the bases of transportation/assignment LPs), a dense block in a sparse frame (a real nucleus), and
badly scaled columns (the pivot threshold has to do work). Usage: SPARSE=build/sparsetest python3 scripts/check_sparse.py"""
import json, os, random, subprocess, sys, zlib
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu

SPARSE = os.environ.get("SPARSE", "build/sparsetest")

def dense_of(m, cols):
    B = np.zeros((m, m))
    for j, (rows, vals) in enumerate(cols):
        for i, v in zip(rows, vals):
            B[i, j] += v
    return B

def random_cols(r, m, per, scale=False):
    cols = []
    perm = list(range(m))
    r.shuffle(perm)
    for j in range(m):
        k = r.randint(1, per)
        rows = {perm[j]}
        while len(rows) < min(k, m):
            rows.add(r.randrange(m))
        rows = sorted(rows)
        s = 10.0 ** r.uniform(-2, 2) if scale else 1.0
        vals = [(r.uniform(0.5, 2.0) * r.choice([-1, 1]) if i == perm[j] else r.uniform(-1, 1)) * s for i in rows]
        cols.append((rows, vals))
    return cols

def network_cols(r, m):
    """Forests of two-entry columns (+1,+1) over m nodes plus one unit column (-1) in each component: nonsingular, nearly triangular."""
    parent = list(range(m))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    cols = []
    for _ in range(r.randint(0, m)):
        a, b = r.randrange(m), r.randrange(m)
        if a != b and find(a) != find(b):
            parent[find(a)] = find(b)
            cols.append((sorted([a, b]), [1.0, 1.0]))
    seen = set()
    for a in range(m):
        c = find(a)
        if c not in seen:
            seen.add(c)
            comp = [x for x in range(m) if find(x) == c]
            cols.append(([r.choice(comp)], [-1.0]))
    r.shuffle(cols)
    return cols[:m]

def nucleus_cols(r, m):
    cols = network_cols(r, m)
    k = max(3, m // 6)
    core = r.sample(range(m), k)
    for j in r.sample(range(m), k):
        rows = sorted(set(core))
        cols[j] = (rows, [r.uniform(-1, 1) + (3 if i == core[0] else 0) for i in rows])
    return cols

def families(seed):
    r = random.Random(seed)
    out = []
    for t in range(60):
        m = r.randint(1, 40)
        out.append((f"random-{t}", m, random_cols(r, m, r.randint(1, 5))))
    for t in range(20):
        m = r.randint(60, 300)
        out.append((f"random-big-{t}", m, random_cols(r, m, r.randint(2, 6))))
    for t in range(30):
        m = r.randint(2, 200)
        out.append((f"network-{t}", m, network_cols(r, m)))
    for t in range(15):
        m = r.randint(20, 150)
        out.append((f"nucleus-{t}", m, nucleus_cols(r, m)))
    for t in range(20):
        m = r.randint(5, 60)
        out.append((f"scaled-{t}", m, random_cols(r, m, 4, scale=True)))
    for t in range(20):
        m = r.randint(6, 40)
        out.append((f"illcond-{t}", m, illcond_cols(r, m)))
    return out

def good(B, limit=1e6):
    return np.linalg.matrix_rank(B) == B.shape[0] and np.linalg.cond(B, 1) <= limit

def illcond_cols(r, m):
    """A sparse basis with a row singleton whose entry is tiny (1e-8): condition number about 1e8, so only a pivot threshold keeps the residual small."""
    cols = random_cols(r, m, 4)
    row = r.randrange(m)
    keep = None
    for j, (rows, vals) in enumerate(cols):
        if row in rows and keep is None:
            keep = j
    out = []
    for j, (rows, vals) in enumerate(cols):
        if row in rows and j != keep:
            pairs = [(i, v) for i, v in zip(rows, vals) if i != row]
            rows, vals = [i for i, _ in pairs] or [(row + 1) % m], [v for _, v in pairs] or [1.0]
        elif j == keep:
            pairs = [(i, v) for i, v in zip(rows, vals) if i != row] + [(row, 1e-8)]
            pairs.sort()
            rows, vals = [i for i, _ in pairs], [v for _, v in pairs]
        out.append((rows, vals))
    return out

def case_json(m, cols, etas, bs, cs, bh=(), ch=()):
    bstart, bind, bval = [0], [], []
    for rows, vals in cols:
        bind += rows
        bval += vals
        bstart.append(len(bind))
    return {"m": m, "bstart": bstart, "bind": bind, "bval": bval, "etas": [{"r": r_, "rows": rw, "vals": vl} for r_, rw, vl in etas], "ftran": bs, "btran": cs, "ftran_h": list(bh), "btran_h": list(ch)}

def scaled_res(B, x, b, left=False):
    if left:
        res = x @ B - b
        scale = 1 + np.abs(x) @ np.abs(B)
        return np.max(np.abs(res) / np.maximum(1, scale + np.abs(b)))
    res = B @ x - b
    scale = 1 + np.abs(B) @ np.abs(x)
    return np.max(np.abs(res) / np.maximum(1, scale + np.abs(b)))

def run(payload):
    p = subprocess.run([SPARSE], input=json.dumps(payload), capture_output=True, text=True)
    return p

bad = 0
checked = 0
worst = 0.0
nsolves = 0
for name, m, cols in families(int(os.environ.get("SEED", "11"))):
    ill = name.startswith("illcond")
    B = dense_of(m, cols)
    if not good(B, 1e10 if ill else 1e6):
        continue
    r = random.Random(zlib.crc32(name.encode()))
    etas = []
    cur = [c for c in cols]
    for _ in range(0 if ill else r.choice([0, 0, 1, 3, 8, 20])):
        pos = r.randrange(m)
        rows = sorted(r.sample(range(m), min(m, r.randint(1, 4))))
        vals = [r.uniform(-1, 1) + (2 if i == rows[0] else 0) for i in rows]
        trial = list(cur)
        trial[pos] = (rows, vals)
        if good(dense_of(m, trial)):
            # the replacement is given as a column of the new basis; the driver computes its FTRAN and pushes the eta
            etas.append((pos, rows, vals))
            cur = trial
    Bf = dense_of(m, cur)
    bs = [[r.uniform(-1, 1) for _ in range(m)] for _ in range(3)] + [[1.0] * m]
    cs = [[r.uniform(-1, 1) for _ in range(m)] for _ in range(3)] + [[0.0] * (m - 1) + [1.0]]
    # sparse right-hand sides for the hypersparse solves (design.md 21.2): one to six nonzeros, and a unit vector at each end
    def sparse_vec():
        v = [0.0] * m
        for i in r.sample(range(m), min(m, r.randint(1, 6))):
            v[i] = r.uniform(-1, 1) or 0.5
        return v
    bh = [sparse_vec() for _ in range(4)] + [[1.0 if i == 0 else 0.0 for i in range(m)], [1.0 if i == m - 1 else 0.0 for i in range(m)]]
    ch = [sparse_vec() for _ in range(4)] + [[1.0 if i == 0 else 0.0 for i in range(m)], [1.0 if i == m - 1 else 0.0 for i in range(m)]]
    pr = run(case_json(m, cols, etas, bs, cs, bh, ch))
    checked += 1
    if pr.returncode != 0:
        print(f"FAIL {name}: driver status {pr.returncode}: {pr.stderr.strip()[:200]} {pr.stdout.strip()[:200]}")
        bad += 1
        continue
    got = json.loads(pr.stdout)
    if got["status"] != 0 or got["etas"] != len(etas):
        print(f"FAIL {name}: status {got['status']} etas {got['etas']} (wanted 0 and {len(etas)})")
        bad += 1
        continue
    lu = splu(sp.csc_matrix(Bf))
    if got["lmax"] > 10.0 * (1 + 1e-9):
        print(f"FAIL {name}: a multiplier of L is {got['lmax']}, above 1 / threshold = 10")
        bad += 1
    if not etas:
        fill = got["lnz"] + got["unz"] + m
        ref = lu.L.nnz + lu.U.nnz - m
        if not ill and fill > 1.25 * ref + 2:
            print(f"FAIL {name}: nnz(L)+nnz(U) = {fill}, SuperLU {ref} (m={m})")
            bad += 1
        if name.startswith("network") and fill > int((Bf != 0).sum()):
            print(f"FAIL {name}: fill-in on a network basis: {fill} against {int((Bf != 0).sum())} nonzeros")
            bad += 1
    for b, x in zip(bs, got["ftran"]):
        x = np.array(x); b = np.array(b)
        nsolves += 1
        res = scaled_res(Bf, x, b)
        ref = lu.solve(b)
        diff = np.max(np.abs(x - ref)) / (1 + np.max(np.abs(ref)))
        worst = max(worst, res)
        if res > 1e-9 or (diff > 1e-7 and not ill):
            print(f"FAIL {name}: FTRAN residual {res:.2e}, difference from splu {diff:.2e} (m={m}, {len(etas)} etas)")
            bad += 1
    for c, y in zip(cs, got["btran"]):
        y = np.array(y); c = np.array(c)
        nsolves += 1
        res = scaled_res(Bf, y, c, left=True)
        ref = lu.solve(c, trans="T")
        diff = np.max(np.abs(y - ref)) / (1 + np.max(np.abs(ref)))
        worst = max(worst, res)
        if res > 1e-9 or (diff > 1e-7 and not ill):
            print(f"FAIL {name}: BTRAN residual {res:.2e}, difference from splu {diff:.2e} (m={m}, {len(etas)} etas)")
            bad += 1

    for kind, vecs, outs in (("FTRAN_H", bh, got["ftran_h"]), ("BTRAN_H", ch, got["btran_h"])):
        for b, o in zip(vecs, outs):
            x = np.array(o["x"]); b = np.array(b); idx = o["idx"]
            nsolves += 1
            res = scaled_res(Bf, x, b, left=(kind == "BTRAN_H"))
            ref = lu.solve(b, trans="T" if kind == "BTRAN_H" else "N")
            diff = np.max(np.abs(x - ref)) / (1 + np.max(np.abs(ref)))
            worst = max(worst, res)
            if res > 1e-9 or (diff > 1e-7 and not ill):
                print(f"FAIL {name}: {kind} residual {res:.2e}, difference from splu {diff:.2e} (m={m}, {len(etas)} etas)")
                bad += 1
            if not o["same"]:
                print(f"FAIL {name}: {kind} differs from the dense solve of the same vector in at least one bit")
                bad += 1
            if len(set(idx)) != len(idx) or any(not 0 <= i < m for i in idx):
                print(f"FAIL {name}: {kind} list has a repeated or out-of-range index: {idx[:20]}")
                bad += 1
            missing = [i for i in range(m) if x[i] != 0.0 and i not in set(idx)]
            if missing:
                print(f"FAIL {name}: {kind} nonzero entries {missing[:10]} are not in the returned list")
                bad += 1

# a singular basis must be reported, not solved
sing = case_json(3, [([0], [1.0]), ([1], [1.0]), ([1], [2.0])], [], [[1.0, 1.0, 1.0]], [[1.0, 1.0, 1.0]])
pr = run(sing)
if pr.returncode != 0 or json.loads(pr.stdout)["status"] != 1:
    print(f"FAIL singular: {pr.stdout.strip()[:200]}")
    bad += 1

print(f"sparse linear algebra gate: {'FAILED' if bad else 'passed'} ({checked} bases, {nsolves} solves, worst scaled residual {worst:.1e}, {bad} failures)")
sys.exit(1 if bad else 0)
