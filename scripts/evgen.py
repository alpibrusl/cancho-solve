"""The EV-depot model of docs/examples/ev_depot.sol, generated for V vehicles and T slots (docs/design.md section 21), shared by scripts/bench_scaling.py and scripts/check_cuts.py."""
import random

PMAX = 11


def generate(V, T, setting, seed):
    """The story's model for V vehicles and T slots: windows, needs, a binding grid limit, a price dear at the ends and cheap in the middle."""
    rng = random.Random(seed * 1000003 + V * 101 + T)
    third = max(1, T // 3)
    arr, dep, need = [], [], []
    for _ in range(V):
        a = rng.randrange(0, third)
        d = rng.randrange(T - third + 1, T + 1)
        d = max(d, a + T // 2)
        d = min(d, T)
        arr.append(a)
        dep.append(d)
        need.append(max(1, round(rng.uniform(0.25, 0.5) * PMAX * (d - a))))
    mid = (T - 1) / 2
    price = [round(0.10 + 0.20 * abs(t - mid) / mid, 2) for t in range(T)]
    chargers = V if setting == "ample" else max(1, V // 2)
    grid = round(0.5 * PMAX * V)
    avail = [1 if arr[v] <= t < dep[v] else 0 for v in range(V) for t in range(T)]
    rows = ",\n                ".join(", ".join(str(a) for a in avail[v * T:(v + 1) * T]) for v in range(V))
    return f"""// scripts/bench_scaling.py: V={V}, T={T}, {setting} chargers, seed {seed}
param V = {V};
param T = {T};
param chargers = {chargers};
param grid = {grid};
param price = [{", ".join(str(p) for p in price)}];
param need = [{", ".join(str(n) for n in need)}];
param avail = [{rows}];

var charge[0..V, 0..T] : real 0..{PMAX};
var on[0..V, 0..T]     : bool;

minimize cost: sum v in 0..V: sum t in 0..T: price[t] * charge[v,t];

subject to
    forall v in 0..V: energy:   sum t in 0..T: charge[v,t] >= need[v];
    forall v in 0..V: forall t in 0..T: plugged: on[v,t] <= avail[v*T+t];
    forall v in 0..V: forall t in 0..T: link:    charge[v,t] <= {PMAX} * on[v,t];
    forall t in 0..T: chargers_free: sum v in 0..V: on[v,t] <= chargers;
    forall t in 0..T: grid_limit:    sum v in 0..V: charge[v,t] <= grid;
"""
