#!/usr/bin/env python3
"""How sparse is the optimal basis of the benchmark families? (docs/design.md section 18.) For each instance, OR-Tools' GLOP solves the LP and says which columns and rows are
basic (its `basis_status`); the basis matrix B has those structural columns of A and the unit column of each basic row. B is LU-factorised (scipy splu, COLAMD ordering) and the table says how many nonzeros B and L+U have, against m*m,
the cells of an explicit inverse, and m*(n+m), the cells of the tableau. Needs scipy and ortools. Usage: basis_density.py"""
import json, os, sys
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve
from ortools.linear_solver import pywraplp

SOLVE = os.environ.get("SOLVE", "build/solve")
cases = [
    ("random dense LP 200x400", lpgen.random_lp(7, 200, 400, 0.5)),
    ("random dense LP 400x800", lpgen.random_lp(7, 400, 800, 0.5)),
    ("transportation 100x160", lpgen.transportation(7, 100, 160)),
    ("assignment 100x100", lpgen.assignment(7, 100)),
    ("multi-knapsack 2000 items, 100 rows", lpgen.mkp(7, 2000, 100)),
]
print(f"{'instance':38} {'m':>5} {'n':>6} {'nnz(A)':>8} {'basic struct':>12} {'nnz(B)':>7} {'nnz(L+U)':>9} {'m*m':>9} {'m*(n+m)':>10} {'L+U / m*m':>10}")
for name, text in cases:
    p, _ = run_solve(SOLVE, ["expand"], text)
    model = json.loads(p.stdout)
    m, n = len(model["constraints"]), len(model["variables"])
    solver = pywraplp.Solver.CreateSolver("GLOP")
    xs = [solver.NumVar(v["lo"], v["hi"], v["name"]) for v in model["variables"]]
    cons = []
    for r in model["constraints"]:
        lo, hi = (-solver.infinity(), r["rhs"]) if r["sense"] == "<=" else (r["rhs"], solver.infinity()) if r["sense"] == ">=" else (r["rhs"], r["rhs"])
        cc = solver.Constraint(lo, hi)
        for j, a in r["terms"]:
            cc.SetCoefficient(xs[j], a)
        cons.append(cc)
    o = solver.Objective()
    for j, a in model["objective"]["terms"]:
        o.SetCoefficient(xs[j], a)
    o.SetMaximization() if model["objective"]["sense"] == "maximize" else o.SetMinimization()
    assert solver.Solve() == pywraplp.Solver.OPTIMAL
    A = sp.lil_matrix((m, n))
    for i, r in enumerate(model["constraints"]):
        for j, a in r["terms"]:
            A[i, j] = a
    A = A.tocsc()
    basic_cols = [j for j in range(n) if xs[j].basis_status() == pywraplp.Solver.BASIC]
    slack_rows = [i for i, cc in enumerate(cons) if cc.basis_status() == pywraplp.Solver.BASIC]
    cols = [A[:, j] for j in basic_cols]
    for i in slack_rows:
        cols.append(sp.csc_matrix(([1.0], ([i], [0])), shape=(m, 1)))
    assert len(cols) == m, (len(cols), m)
    B = sp.hstack(cols).tocsc()
    try:
        lu = splu(B, permc_spec="COLAMD")
        fill = lu.L.nnz + lu.U.nnz
    except RuntimeError:
        fill = -1
    print(f"{name:38} {m:5d} {n:6d} {A.nnz:8d} {len(basic_cols):12d} {B.nnz:7d} {fill:9d} {m*m:9d} {m*(n+m):10d} {fill / (m*m):10.3f}")
