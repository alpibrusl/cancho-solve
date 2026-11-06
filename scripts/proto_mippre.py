"""Prototype MIP presolve in Python: reads `solve expand` JSON, reduces, writes .sol text for the unchanged solver."""
import sys, json, math, subprocess
sys.path.insert(0, "scripts")
from gen_models import sh
INF = 1e300
def reduce(ex, rounds=20):
    nv = len(ex["variables"])
    lo = [v["lo"] for v in ex["variables"]]; hi = [v["hi"] for v in ex["variables"]]
    isint = [v["kind"] in ("bool", "int") for v in ex["variables"]]
    sign = -1.0 if ex["objective"]["sense"] == "maximize" else 1.0
    cost = [0.0] * nv
    for j, a in ex["objective"]["terms"]: cost[j] += sign * a
    rows = []
    for r in ex["constraints"]:
        t = {}
        for j, a in r["terms"]: t[j] = t.get(j, 0.0) + a
        s, b = r["sense"], r["rhs"]
        rows.append([t, b if s in (">=", "==") else -INF, b if s in ("<=", "==") else INF])
    live = [True] * len(rows); fixedv = {}
    for it in range(rounds):
        changed = False
        for i, (t, rlo, rhi) in enumerate(rows):
            if not live[i]: continue
            # substitute fixed columns
            for j in [j for j in t if lo[j] == hi[j]]:
                a = t.pop(j); sh_ = a * lo[j]
                if rlo > -INF: rlo -= sh_
                if rhi < INF: rhi -= sh_
                rows[i][1], rows[i][2] = rlo, rhi; changed = True
            tol = lambda b: 1e-9 * (1 + abs(b))
            if not t:
                if rlo > tol(rlo) and rlo > -INF or rhi < -tol(rhi) and rhi < INF: raise SystemExit("infeasible")
                live[i] = False; changed = True; continue
            amin = sum(a * (lo[j] if a > 0 else hi[j]) for j, a in t.items())
            amax = sum(a * (hi[j] if a > 0 else lo[j]) for j, a in t.items())
            if amin >= rlo - tol(rlo) and amax <= rhi + tol(rhi):
                live[i] = False; changed = True; continue
            if amin > rhi + tol(rhi) or amax < rlo - tol(rlo): raise SystemExit("infeasible")
            if len(t) == 1:
                (j, a), = t.items()
                l2 = (rlo / a if a > 0 else rhi / a) if (rlo > -INF if a > 0 else rhi < INF) else -INF
                h2 = (rhi / a if a > 0 else rlo / a) if (rhi < INF if a > 0 else rlo > -INF) else INF
                if isint[j]:
                    if l2 > -INF: l2 = math.ceil(l2 - 1e-9)
                    if h2 < INF: h2 = math.floor(h2 + 1e-9)
                lo[j] = max(lo[j], l2); hi[j] = min(hi[j], h2)
                if lo[j] > hi[j] + 1e-9: raise SystemExit("infeasible")
                if lo[j] > hi[j]: hi[j] = lo[j]
                live[i] = False; changed = True
        # dual fixing
        for j in range(nv):
            if lo[j] == hi[j]: continue
            down_ok = up_ok = True
            for i, (t, rlo, rhi) in enumerate(rows):
                if not live[i] or j not in t: continue
                a = t[j]
                # lowering x_j harmless if (a>0 and no lower side) or (a<0 and no upper side)
                if not ((a > 0 and rlo <= -INF) or (a < 0 and rhi >= INF)): down_ok = False
                if not ((a > 0 and rhi >= INF) or (a < 0 and rlo <= -INF)): up_ok = False
            if cost[j] >= 0 and down_ok: hi[j] = lo[j]; changed = True
            elif cost[j] <= 0 and up_ok: lo[j] = hi[j]; changed = True
        if not changed: break
    return lo, hi, isint, cost, rows, live, sign
def emit(ex, lo, hi, isint, cost, rows, live, sign):
    nv = len(lo)
    const = ex["objective"]["constant"]
    keep = []
    for j in range(nv):
        if lo[j] == hi[j]: const += sign * 0 + 0  # fixed columns contribute cost*value
    fixed_cost = sum(cost[j] * lo[j] for j in range(nv) if lo[j] == hi[j])
    used = set()
    for i, (t, a, b) in enumerate(rows):
        if live[i]:
            for j in t:
                if lo[j] != hi[j]: used.add(j)
    objcols = [j for j in range(nv) if lo[j] != hi[j]]
    L = []
    for j in objcols:
        if isint[j] and lo[j] == 0 and hi[j] == 1: L.append(f"var x{j} : bool;")
        elif isint[j]: L.append(f"var x{j} : int {int(lo[j])}..{int(hi[j])};")
        else: L.append(f"var x{j} : real {lo[j]:.12g}..{hi[j]:.12g};")
    def expr(t):
        s = ""
        for j, a in t:
            if lo[j] == hi[j]: continue
            if s == "": s = f"{a:.12g}*x{j}"
            else: s += (f" + {a:.12g}*x{j}" if a >= 0 else f" - {-a:.12g}*x{j}")
        return s
    ot = [(j, cost[j]) for j in objcols if cost[j] != 0]
    ocon = fixed_cost * 1.0
    # objective in minimised form; sense minimize regardless; constant = original const*sign + fixed cost; report back via sign
    oc = sign * const + fixed_cost
    oe = expr(ot) or "0*x%d" % objcols[0]
    L.append(f"minimize total: {oe} + {oc:.12g};")
    L.append("subject to")
    k = 0
    for i, (t, rlo, rhi) in enumerate(rows):
        if not live[i]: continue
        e = expr(list(t.items()))
        if not e: continue
        if rlo == rhi: L.append(f"    r{k}: {e} == {rlo:.12g};")
        else:
            if rlo > -INF: L.append(f"    r{k}: {e} >= {rlo:.12g};"); k += 1
            if rhi < INF: L.append(f"    r{k}: {e} <= {rhi:.12g};")
        k += 1
    return "\n".join(L) + "\n", len(objcols), sum(live)
if __name__ == "__main__":
    from evgen import generate
    V, T, seed = map(int, sys.argv[1:4])
    text = generate(V, T, "tight", seed)
    ex = json.loads(sh(["expand"], text).stdout)
    red = reduce(ex)
    out, nc, nr = emit(ex, *red)
    print(f"{len(ex['variables'])} cols {len(ex['constraints'])} rows -> {nc} cols {nr} rows", file=sys.stderr)
    open(sys.argv[4], "w").write(out)
