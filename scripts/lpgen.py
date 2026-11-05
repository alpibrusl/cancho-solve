"""Instance generators shared by check_highs.py and bench_highs.py. Every function returns the text of a `.sol` model; the seed fixes it."""
import random

def _num(x):
    return str(int(x)) if x == int(x) else repr(x)

def _expr(coefs, names):
    out = []
    for c, v in zip(coefs, names):
        if c == 0:
            continue
        out.append(("+ " if c > 0 else "- ") + (f"{_num(abs(c))}*" if abs(c) != 1 else "") + v)
    if not out:
        return "0*" + names[0]
    s = " ".join(out)
    return s[2:] if s.startswith("+ ") else "-" + s[2:]

def random_lp(seed, m, n, density=0.5, infeasible=False):
    """Boxed variables, rows of the three senses, rhs built from a hidden integer point so the model is feasible unless `infeasible`."""
    r = random.Random(seed)
    names = [f"v{j}" for j in range(n)]
    lo = [r.randint(-5, 2) for _ in range(n)]
    hi = [l + r.randint(1, 8) for l in lo]
    x0 = [r.randint(l, h) for l, h in zip(lo, hi)]
    lines = [f"var {v} : real {l}..{h};" for v, l, h in zip(names, lo, hi)]
    c = [r.randint(-9, 9) for _ in range(n)]
    lines.append(("minimize " if r.random() < 0.5 else "maximize ") + _expr(c, names) + ";")
    lines.append("subject to")
    for i in range(m):
        a = [r.randint(-9, 9) if r.random() < density else 0 for _ in range(n)]
        if not any(a):
            a[r.randrange(n)] = 1
        act = sum(ai * xi for ai, xi in zip(a, x0))
        k = r.random()
        if k < 0.4:
            op, rhs = "<=", act + r.randint(0, 6)
        elif k < 0.8:
            op, rhs = ">=", act - r.randint(0, 6)
        else:
            op, rhs = "==", act
        lines.append(f"    c{i}: {_expr(a, names)} {op} {rhs};")
    if infeasible:
        j = r.randrange(n)
        lines.append(f"    cut: {names[j]} >= {hi[j] + 1};")
    return "\n".join(lines) + "\n"

def transportation(seed, s, d):
    r = random.Random(seed)
    dem = [r.randint(5, 30) for _ in range(d)]
    total = sum(dem)
    sup = [total // s + r.randint(3, 12) for _ in range(s)]
    cost = [r.randint(1, 40) for _ in range(s * d)]
    return (f"param s = {s};\nparam d = {d};\nparam sup = [{', '.join(map(str, sup))}];\nparam dem = [{', '.join(map(str, dem))}];\n"
            f"param cost = [{', '.join(map(str, cost))}];\n"
            f"var f[0..s, 0..d] : real 0..{max(sup)};\n"
            "minimize total: sum i in 0..s: sum j in 0..d: cost[i*d+j] * f[i,j];\n"
            "subject to\n"
            "    forall i in 0..s: supply: sum j in 0..d: f[i,j] <= sup[i];\n"
            "    forall j in 0..d: demand: sum i in 0..s: f[i,j] >= dem[j];\n")

def assignment(seed, n):
    r = random.Random(seed)
    cost = [r.randint(1, 50) for _ in range(n * n)]
    return (f"param n = {n};\nparam c = [{', '.join(map(str, cost))}];\nvar a[0..n, 0..n] : bool;\n"
            "minimize cost: sum i in 0..n: sum j in 0..n: c[i*n+j] * a[i,j];\n"
            "subject to\n"
            "    forall i in 0..n: row: sum j in 0..n: a[i,j] == 1;\n"
            "    forall j in 0..n: col: sum i in 0..n: a[i,j] == 1;\n")

def mkp(seed, n, k):
    """Multi-dimensional knapsack; the relaxation is the LP."""
    r = random.Random(seed)
    w = [r.randint(5, 40) for _ in range(n * k)]
    v = [r.randint(10, 60) for _ in range(n)]
    cap = [sum(w[i * n:(i + 1) * n]) // 3 for i in range(k)]
    return (f"param n = {n};\nparam k = {k};\nparam w = [{', '.join(map(str, w))}];\nparam v = [{', '.join(map(str, v))}];\n"
            f"param cap = [{', '.join(map(str, cap))}];\nvar x[0..n] : bool;\n"
            "maximize value: sum j in 0..n: v[j] * x[j];\n"
            "subject to\n"
            "    forall i in 0..k: cap_i: sum j in 0..n: w[i*n+j] * x[j] <= cap[i];\n")

def mincost_flow(seed, nodes, arcs, cap=100):
    """A min-cost flow LP: `arcs` random arcs (a Hamiltonian cycle first, so the graph is connected), one conservation row for each node (out - in == supply), the supplies
    those of a hidden random flow, so the model is feasible. Rows are written out term by term: nodes x arcs-per-node terms in all (2 per arc)."""
    r = random.Random(seed)
    order = list(range(nodes))
    r.shuffle(order)
    ends = [(order[k], order[(k + 1) % nodes]) for k in range(nodes)]
    while len(ends) < arcs:
        a, b = r.randrange(nodes), r.randrange(nodes)
        if a != b:
            ends.append((a, b))
    ends = ends[:max(arcs, nodes)]
    a_n = len(ends)
    flow = [r.randint(0, cap // 2) for _ in range(a_n)]
    supply = [0] * nodes
    out_terms = [[] for _ in range(nodes)]
    for e, (a, b) in enumerate(ends):
        supply[a] += flow[e]
        supply[b] -= flow[e]
        out_terms[a].append((e, 1))
        out_terms[b].append((e, -1))
    cost = [r.randint(1, 50) for _ in range(a_n)]
    lines = [f"param a = {a_n};", f"param cost = [{', '.join(map(str, cost))}];", f"var f[0..a] : real 0..{cap};",
             "minimize total: sum e in 0..a: cost[e] * f[e];", "subject to"]
    for v in range(nodes):
        lhs = " ".join(("+ " if s > 0 else "- ") + f"f[{e}]" for e, s in out_terms[v])
        lhs = lhs[2:] if lhs.startswith("+ ") else "-" + lhs[2:]
        lines.append(f"    n{v}: {lhs} == {supply[v]};")
    return "\n".join(lines) + "\n"

# ---- S3 (docs/design.md section 19): mixed-integer families --------------------------------------------------------------------------------------------

def knapsack(seed, n, correlated=True):
    """0/1 knapsack, `maximize`, one row. Correlated values (v = w + noise) make the relaxation's gap hard for branch and bound."""
    r = random.Random(seed)
    w = [r.randint(10, 60) for _ in range(n)]
    v = [x + r.randint(0, 10) if correlated else r.randint(10, 80) for x in w]
    cap = sum(w) // 2
    return (f"param n = {n};\nparam w = [{', '.join(map(str, w))}];\nparam v = [{', '.join(map(str, v))}];\nvar x[0..n] : bool;\n"
            "maximize value: sum j in 0..n: v[j] * x[j];\nsubject to\n"
            f"    cap: sum j in 0..n: w[j] * x[j] <= {cap};\n")

def set_cover(seed, m, n, density=0.15):
    """Minimise the cost of the sets (columns) that cover every element (row) at least once. Every row gets at least one column, so it is feasible."""
    r = random.Random(seed)
    cost = [r.randint(1, 20) for _ in range(n)]
    rows = []
    for i in range(m):
        cols = [j for j in range(n) if r.random() < density]
        if not cols:
            cols = [r.randrange(n)]
        rows.append(cols)
    lines = [f"param c = [{', '.join(map(str, cost))}];", f"var s[0..{n}] : bool;", "minimize cost: sum j in 0..%d: c[j] * s[j];" % n, "subject to"]
    for i, cols in enumerate(rows):
        lines.append(f"    cover{i}: " + " + ".join(f"s[{j}]" for j in cols) + " >= 1;")
    return "\n".join(lines) + "\n"

def random_mip(seed, m, n, density=0.6, int_frac=1.0, infeasible=False):
    """Like random_lp, but a fraction `int_frac` of the variables are `int` (the rest `real`); the right sides come from a hidden point that is whole on the
    integer columns, so the model is feasible unless `infeasible` (a row that no point in the box satisfies)."""
    r = random.Random(seed)
    names = [f"v{j}" for j in range(n)]
    isint = [r.random() < int_frac for _ in range(n)]
    lo = [r.randint(-3, 2) for _ in range(n)]
    hi = [l + r.randint(1, 9) for l in lo]
    x0 = [r.randint(l, h) for l, h in zip(lo, hi)]
    lines = [f"var {v} : {'int' if k else 'real'} {l}..{h};" for v, k, l, h in zip(names, isint, lo, hi)]
    c = [r.randint(-9, 9) for _ in range(n)]
    lines.append(("minimize " if r.random() < 0.5 else "maximize ") + _expr(c, names) + ";")
    lines.append("subject to")
    for i in range(m):
        a = [r.randint(-9, 9) if r.random() < density else 0 for _ in range(n)]
        if not any(a):
            a[r.randrange(n)] = 1
        act = sum(ai * xi for ai, xi in zip(a, x0))
        k = r.random()
        if k < 0.45:
            op, rhs = "<=", act + r.randint(0, 6)
        elif k < 0.9:
            op, rhs = ">=", act - r.randint(0, 6)
        else:
            op, rhs = "==", act
        lines.append(f"    c{i}: {_expr(a, names)} {op} {rhs};")
    if infeasible:
        j = r.randrange(n)
        lines.append(f"    cut: {names[j]} >= {hi[j] + 1};")
    return "\n".join(lines) + "\n"

def equality_knapsack(seed, n, feasible=True):
    """Subset-sum style: pick items so that the weights sum to exactly `target`, maximising the number picked. With `feasible` False every weight is even and the target odd,
    so the model has no integer point while its relaxation has one."""
    r = random.Random(seed)
    w = [r.randint(5, 40) for _ in range(n)]
    if feasible:
        pick = [j for j in range(n) if r.random() < 0.4] or [0]
        target = sum(w[j] for j in pick)
    else:
        w = [2 * x for x in w]
        target = sum(w) // 3 | 1
    return (f"param n = {n};\nparam w = [{', '.join(map(str, w))}];\nvar x[0..n] : bool;\nmaximize picked: sum j in 0..n: x[j];\nsubject to\n"
            f"    target: sum j in 0..n: w[j] * x[j] == {target};\n")

def bin_packing_lite(seed, items, bins):
    """Assign items of integer size to a few bins of fixed capacity, minimising the number of bins opened: a symmetric model that is hard for plain branch and bound."""
    r = random.Random(seed)
    size = [r.randint(3, 9) for _ in range(items)]
    cap = 12
    lines = [f"param sz = [{', '.join(map(str, size))}];", f"var a[0..{items}, 0..{bins}] : bool;", f"var u[0..{bins}] : bool;", f"minimize bins: sum b in 0..{bins}: u[b];", "subject to"]
    lines.append(f"    forall i in 0..{items}: one: sum b in 0..{bins}: a[i,b] == 1;")
    lines.append(f"    forall b in 0..{bins}: capacity: sum i in 0..{items}: sz[i] * a[i,b] - {cap} * u[b] <= 0;")
    return "\n".join(lines) + "\n"
