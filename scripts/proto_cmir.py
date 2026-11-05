#!/usr/bin/env python3
"""Prototype for docs/design.md 21.2: how far do mixed-integer-rounding cuts with path aggregation (Marchand and Wolsey) lift the root bound of a model, in dense numpy over scipy's HiGHS LP?
It is the reference the cancho code (lib/mip/cmir.cho) is written against, and the source of the numbers 21.2 quotes for the prototype. Not a gate and not used by one.

For each model: the LP bound, the bound after the implied cuts of 19.8 (rebuilt here), then rounds of: solve the LP, separate, add the best PER cuts; the bound every 10 rounds; the optimum of HiGHS for reference.
A model is a .sol file, or `ev:V:T` for the tight EV-depot model of scripts/evgen.py (seed 7).
Usage: python3 scripts/proto_cmir.py MODEL.sol|ev:V:T [...] [--rounds 150] [--per 150] [--maxagg 8]   (SOLVE=build/solve reads the models through `solve expand`)"""
import argparse, json, math, os, subprocess, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scipy.optimize import linprog, milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

ap = argparse.ArgumentParser()
ap.add_argument("models", nargs="+")
ap.add_argument("--rounds", type=int, default=150)
ap.add_argument("--per", type=int, default=150)
ap.add_argument("--maxagg", type=int, default=8)
args = ap.parse_args()
SOLVE = os.environ.get("SOLVE", "build/solve")


def load(path):
    if path.startswith("ev:"):
        from evgen import generate
        _, v, t = path.split(":")
        text = generate(int(v), int(t), "tight", 7)
    else:
        text = open(path).read()
    model = json.loads(subprocess.run([SOLVE, "expand"], input=text, capture_output=True, text=True).stdout)
    n = len(model["variables"])
    c = np.zeros(n)
    for j, a in model["objective"]["terms"]:
        c[j] += a
    D = np.zeros((len(model["constraints"]), n))
    sense, rhs = [], []
    for r, row in enumerate(model["constraints"]):
        for j, a in row["terms"]:
            D[r, j] += a
        sense.append(row["sense"])
        rhs.append(row["rhs"])
    lo = np.array([v["lo"] for v in model["variables"]], float)
    hi = np.array([v["hi"] for v in model["variables"]], float)
    isint = np.array([v["kind"] in ("bool", "int") for v in model["variables"]])
    return model, c, D, sense, np.array(rhs, float), lo, hi, isint


def le_form(D, sense, rhs):
    rows, b = [], []
    for i, t in enumerate(sense):
        if t in ("<=", "=="):
            rows.append(D[i]); b.append(rhs[i])
        if t in (">=", "=="):
            rows.append(-D[i]); b.append(-rhs[i])
    return np.array(rows), np.array(b)


def vub_map(R, b, isint):
    vub = {}
    for i in range(R.shape[0]):
        nz = np.nonzero(R[i])[0]
        if len(nz) == 2 and abs(b[i]) < 1e-12:
            for x_, y_ in ((nz[0], nz[1]), (nz[1], nz[0])):
                if not isint[x_] and isint[y_] and R[i, x_] > 0 and R[i, y_] < 0:
                    vub[x_] = (y_, -R[i, y_] / R[i, x_])
    return vub


def implied_cuts(R, b, isint, vub, lo, hi):
    """The covering-row cuts of 19.8 (single rows, d = largest weight), as <= rows."""
    out = []
    for i in range(R.shape[0]):
        a = -R[i]; rhs = -b[i]          # a x >= rhs
        w = {}; ok = True; used = False
        for j in np.nonzero(a)[0]:
            if a[j] > 0:
                if isint[j]:
                    w[j] = w.get(j, 0) + a[j]
                elif j in vub:
                    y_, u_ = vub[j]; w[y_] = w.get(y_, 0) + a[j] * u_; used = True
                elif np.isfinite(hi[j]):
                    rhs -= a[j] * hi[j]
                else:
                    ok = False
            else:
                if np.isfinite(lo[j]):
                    rhs -= a[j] * lo[j]
                else:
                    ok = False
        if ok and used and len(w) >= 2 and rhs > 1e-9 and min(w.values()) > 1e-9:
            d = max(w.values())
            cut = np.zeros(R.shape[1])
            for j, v in w.items():
                cut[j] = -math.ceil(v / d - 1e-9)
            r2 = math.ceil(rhs / d - 1e-9)
            if r2 >= 1:
                out.append((cut, -r2))
    return out


def mir_from(agg, bg, x, vub, lo, hi, isint):
    n = len(x)
    cs, extra, rhs2 = {}, {}, bg
    for j in np.nonzero(agg)[0]:
        a = agg[j]
        if isint[j]:
            extra[j] = extra.get(j, 0.0) + a
            continue
        opts = [("lb", x[j] - lo[j] if np.isfinite(lo[j]) else 1e18)]
        if np.isfinite(hi[j]):
            opts.append(("ub", hi[j] - x[j]))
        if j in vub:
            opts.append(("vub", vub[j][1] * x[vub[j][0]] - x[j]))
        kind = min(opts, key=lambda t: t[1])[0]
        if kind == "lb":
            if not np.isfinite(lo[j]):
                return None
            rhs2 -= a * lo[j]; cs[(j, "lb")] = a
        elif kind == "ub":
            rhs2 -= a * hi[j]; cs[(j, "ub")] = -a
        else:
            y_, u_ = vub[j]
            extra[y_] = extra.get(y_, 0.0) + a * u_; cs[(j, "vub")] = -a
    yc = {}
    for j, a in extra.items():
        comp = x[j] > 0.5 * (lo[j] + hi[j]) if np.isfinite(hi[j]) else False
        if not (np.isfinite(lo[j]) or np.isfinite(hi[j])):
            return None
        if comp:
            rhs2 -= a * hi[j]; yc[j] = (-a, True)
        else:
            rhs2 -= a * lo[j]; yc[j] = (a, False)
    neg = {k: v for k, v in cs.items() if v < 0}
    cands = {abs(a) for j, (a, comp) in yc.items() if abs(a) > 1e-9 and 1e-6 < abs((hi[j] - x[j]) if comp else (x[j] - lo[j])) < hi[j] - lo[j] - 1e-6}
    if not cands:
        cands = {abs(a) for j, (a, comp) in yc.items() if abs(a) > 1e-9}
    best = None
    for d0 in sorted(cands)[:6]:
        for div in (1, 2, 4, 8):
            d = d0 / div
            bd = rhs2 / d
            f0 = bd - math.floor(bd + 1e-9)
            if f0 < 0.05 or f0 > 0.95:
                continue
            cy, lhs = {}, 0.0
            for j, (a, comp) in yc.items():
                aj = a / d; fj = aj - math.floor(aj + 1e-9)
                cy[j] = math.floor(aj + 1e-9) + max(0.0, fj - f0) / (1 - f0)
                lhs += cy[j] * ((hi[j] - x[j]) if comp else (x[j] - lo[j]))
            sv = {}
            for (j, kind), cv in neg.items():
                s_ = x[j] - lo[j] if kind == "lb" else (hi[j] - x[j] if kind == "ub" else vub[j][1] * x[vub[j][0]] - x[j])
                sv[(j, kind)] = cv / (d * (1 - f0)); lhs += sv[(j, kind)] * s_
            viol = lhs - math.floor(bd + 1e-9)
            eff = viol / max(math.sqrt(sum(v * v for v in cy.values()) + sum(v * v for v in sv.values())), 1e-9)
            if viol > 1e-5 and (best is None or eff > best[0]):
                best = (eff, cy, sv, math.floor(bd + 1e-9))
    if best is None:
        return None
    eff, cy, sv, rb = best
    cx = np.zeros(n); rh = float(rb)
    for j, cv in cy.items():
        if yc[j][1]:
            rh -= cv * hi[j]; cx[j] -= cv
        else:
            rh += cv * lo[j]; cx[j] += cv
    for (j, kind), cv in sv.items():
        if kind == "lb":
            cx[j] += cv; rh += cv * lo[j]
        elif kind == "ub":
            cx[j] -= cv; rh -= cv * hi[j]
        else:
            y_, u_ = vub[j]; cx[y_] += cv * u_; cx[j] -= cv
    return cx, rh, eff


def separate(R, b, x, vub, lo, hi, isint):
    cuts, slack = [], b - R @ x
    for i in np.argsort(slack)[:min(len(b), 400)]:
        agg, bg, used = R[i].copy(), b[i], {i}
        for _ in range(args.maxagg + 1):
            r_ = mir_from(agg, bg, x, vub, lo, hi, isint)
            if r_ is not None:
                cuts.append((r_[2], r_[0], r_[1])); break
            cand = None
            for j in np.nonzero(agg)[0]:
                if isint[j]:
                    continue
                dist = min(x[j] - lo[j], (hi[j] - x[j]) if np.isfinite(hi[j]) else 1e9, (vub[j][1] * x[vub[j][0]] - x[j]) if j in vub else 1e9)
                if dist > 1e-6 and (cand is None or dist > cand[0]):
                    cand = (dist, j)
            if cand is None:
                break
            j = cand[1]
            k = next((k for k in range(R.shape[0]) if k not in used and abs(R[k, j]) > 1e-9 and slack[k] <= 1e-6 and R[k, j] * agg[j] < 0), None)
            if k is None:
                break
            mult = -agg[j] / R[k, j]
            agg = agg + mult * R[k]; bg = bg + mult * b[k]; agg[j] = 0.0
            used.add(k)
    return cuts


for path in args.models:
    model, c, D, sense, rhs, lo, hi, isint = load(path)
    n = len(c)
    R, b = le_form(D, sense, rhs)
    vub = vub_map(R, b, isint)
    t0 = time.time()
    lp0 = linprog(c, A_ub=R, b_ub=b, bounds=list(zip(lo, hi)), method="highs").fun
    imp = implied_cuts(R, b, isint, vub, lo, hi)
    R = np.vstack([R] + [cu[None, :] for cu, _ in imp]) if imp else R
    b = np.concatenate([b, [r_ for _, r_ in imp]]) if imp else b
    base = linprog(c, A_ub=R, b_ub=b, bounds=list(zip(lo, hi)), method="highs").fun
    ref = milp(c, constraints=LinearConstraint(R, -np.inf, b), integrality=isint.astype(int), bounds=Bounds(lo, hi), options=dict(mip_rel_gap=1e-9, time_limit=60))
    print(f"{os.path.basename(path)}: LP {lp0:.4f}  with implied cuts ({len(imp)}) {base:.4f}  optimum (HiGHS) {ref.fun:.4f}")
    added = 0
    for rnd in range(args.rounds):
        res = linprog(c, A_ub=R, b_ub=b, bounds=list(zip(lo, hi)), method="highs")
        x = res.x
        cs = sorted(separate(R, b, x, vub, lo, hi, isint), key=lambda t: -t[0])[:args.per]
        if rnd % 10 == 9 or not cs:
            print(f"  round {rnd + 1:3d}: bound {res.fun:.4f}  fractional {int((isint & (np.abs(x - np.round(x)) > 1e-6)).sum())}  cuts so far {added}  {time.time() - t0:.1f}s")
        if not cs:
            break
        R = np.vstack([R] + [cx[None, :] for _, cx, _ in cs]); b = np.concatenate([b, [rh for _, _, rh in cs]]); added += len(cs)
