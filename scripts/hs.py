"""Common code for the HiGHS oracle (through scipy.optimize.linprog): read `solve expand` JSON, build the LP, solve it, re-check a solution."""
import json, os, subprocess, time
import numpy as np
from scipy.optimize import linprog

def run_solve(solve, verb_args, text):
    # SOLVE_METHOD=dense|sparse|auto makes every gate judge that method of `solve run` (docs/design.md 18.3.2)
    if os.environ.get("SOLVE_METHOD") and verb_args[:1] == ["run"]:
        verb_args = [*verb_args, "--method", os.environ["SOLVE_METHOD"]]
    t = time.perf_counter()
    p = subprocess.run([solve, *verb_args], input=text, capture_output=True, text=True)
    return p, time.perf_counter() - t

def build(model):
    """-> c (minimisation), A_ub, b_ub, A_eq, b_eq, bounds, constant, sign (+1 minimise, -1 maximise)"""
    n = len(model["variables"])
    obj = model["objective"]
    sign = 1.0 if obj is None or obj["sense"] == "minimize" else -1.0
    c = np.zeros(n)
    const = 0.0
    if obj is not None:
        for j, a in obj["terms"]:
            c[j] = sign * a
        const = obj["constant"]
    ub_rows, ub_rhs, eq_rows, eq_rhs = [], [], [], []
    for row in model["constraints"]:
        a = np.zeros(n)
        for j, v in row["terms"]:
            a[j] = v
        if row["sense"] == "<=":
            ub_rows.append(a); ub_rhs.append(row["rhs"])
        elif row["sense"] == ">=":
            ub_rows.append(-a); ub_rhs.append(-row["rhs"])
        else:
            eq_rows.append(a); eq_rhs.append(row["rhs"])
    bounds = [(v["lo"], v["hi"]) for v in model["variables"]]
    A_ub = np.array(ub_rows) if ub_rows else None
    A_eq = np.array(eq_rows) if eq_rows else None
    return c, A_ub, (np.array(ub_rhs) if ub_rows else None), A_eq, (np.array(eq_rhs) if eq_rows else None), bounds, const, sign

def highs(model, method="highs"):
    c, A_ub, b_ub, A_eq, b_eq, bounds, const, sign = build(model)
    t = time.perf_counter()
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method=method)
    dt = time.perf_counter() - t
    obj = None if res.status != 0 else sign * res.fun + const
    return res.status, obj, dt, getattr(res, "nit", None)

def violation(model, x):
    """Largest violation of a bound or a row by x (dict name -> value), recomputed from the expanded model alone."""
    worst = 0.0
    vals = []
    for v in model["variables"]:
        xv = x[v["name"]]
        vals.append(xv)
        worst = max(worst, v["lo"] - xv, xv - v["hi"])
    for row in model["constraints"]:
        act = sum(vals[j] * a for j, a in row["terms"])
        d = act - row["rhs"]
        scale = 1.0 + abs(row["rhs"])
        if row["sense"] == "<=":
            worst = max(worst, d / scale)
        elif row["sense"] == ">=":
            worst = max(worst, -d / scale)
        else:
            worst = max(worst, abs(d) / scale)
    return worst

def objective_of(model, x):
    obj = model["objective"]
    if obj is None:
        return 0.0
    names = [v["name"] for v in model["variables"]]
    return obj["constant"] + sum(a * x[names[j]] for j, a in obj["terms"])

# ---- S3: the MIP oracle (HiGHS through scipy.optimize.milp) and an independent re-check of integrality -----------------------------------------------------

def highs_mip(model, time_limit=None):
    """-> (status, objective in the model's sense or None, seconds, node count or None). status: 0 optimal, 2 infeasible, 1 limit, 3 other (as scipy's milp)."""
    from scipy.optimize import milp, LinearConstraint, Bounds
    n = len(model["variables"])
    c, A_ub, b_ub, A_eq, b_eq, bounds, const, sign = build(model)
    cons = []
    if A_ub is not None:
        cons.append(LinearConstraint(A_ub, -np.inf, b_ub))
    if A_eq is not None:
        cons.append(LinearConstraint(A_eq, b_eq, b_eq))
    integ = np.array([0 if v["kind"] == "real" else 1 for v in model["variables"]])
    opts = {"mip_rel_gap": 0.0}  # HiGHS stops at a relative gap of 1e-4 by default; ours proves optimality, so the oracle is asked to as well
    if time_limit is not None:
        opts["time_limit"] = time_limit
    t = time.perf_counter()
    res = milp(c, constraints=cons, integrality=integ, bounds=Bounds([b[0] for b in bounds], [b[1] for b in bounds]), options=opts)
    dt = time.perf_counter() - t
    obj = None if res.x is None else sign * float(res.fun) + const
    return res.status, obj, dt, getattr(res, "mip_node_count", None)

def int_violation(model, x):
    """Largest distance of an integer column's value from a whole number."""
    worst = 0.0
    for v in model["variables"]:
        if v["kind"] != "real":
            worst = max(worst, abs(x[v["name"]] - round(x[v["name"]])))
    return worst

def brute_force(model, limit=200000):
    """Exhaustive search over a model whose variables are all integer and whose box is small: -> (best objective in the model's sense or None for infeasible), or 'big'.
    Shares no code with the solver or with HiGHS."""
    import itertools
    vs = model["variables"]
    size = 1
    for v in vs:
        if v["kind"] == "real":
            return "big"
        size *= int(v["hi"] - v["lo"] + 1)
        if size > limit:
            return "big"
    obj = model["objective"]
    best = None
    for pt in itertools.product(*[range(int(v["lo"]), int(v["hi"]) + 1) for v in vs]):
        if all((sum(pt[j] * a for j, a in r["terms"]) <= r["rhs"] if r["sense"] == "<=" else
                sum(pt[j] * a for j, a in r["terms"]) >= r["rhs"] if r["sense"] == ">=" else
                sum(pt[j] * a for j, a in r["terms"]) == r["rhs"]) for r in model["constraints"]):
            val = (obj["constant"] + sum(pt[j] * a for j, a in obj["terms"])) if obj else 0.0
            if best is None or (val < best if (obj is None or obj["sense"] == "minimize") else val > best):
                best = val
    return best
