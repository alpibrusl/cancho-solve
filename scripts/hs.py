"""Common code for the HiGHS oracle (through scipy.optimize.linprog): read `solve expand` JSON, build the LP, solve it, re-check a solution."""
import json, subprocess, time
import numpy as np
from scipy.optimize import linprog

def run_solve(solve, verb_args, text):
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
