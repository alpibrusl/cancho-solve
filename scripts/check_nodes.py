#!/usr/bin/env python3
"""Gate 7 (docs/design.md section 19.2): the search is judged by the work it does. The oracle cannot see a worse branching rule, a weaker cut or a wrong node order (the optimum is
the same), so the node and iteration counts of fixed instances under every option are held exactly: the search is deterministic, and a deliberate change of a rule moves these
numbers on purpose and they are then re-measured (docs/design.md 19.5). `--print` prints the table to paste."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve

SOLVE = os.environ.get("SOLVE", "build/solve")
CFGS = {"default": [], "depth+fractional": ["--node-select", "depth", "--branching", "fractional"], "best+fractional": ["--branching", "fractional"], "depth+pseudo": ["--node-select", "depth"],
        "whole-cut off": ["--experiment", "1"], "no rounding": ["--experiment", "2"], "far child": ["--experiment", "4"]}
INSTS = {"mkp 50x10": lpgen.mkp(7, 50, 10), "general int 20x20": lpgen.random_mip(7, 20, 20, 0.4, 1.0), "bin packing 8/4": lpgen.bin_packing_lite(7, 8, 4),
         "knapsack 100": lpgen.knapsack(7, 100), "set cover 120x200": lpgen.set_cover(7, 120, 200, 0.05), "mixed 30x40": lpgen.random_mip(7, 30, 40, 0.3, 0.5)}
EXACT_DENSE = {
    ('mkp 50x10', 'default'): (263, 1287),
    ('mkp 50x10', 'depth+fractional'): (269, 1286),
    ('mkp 50x10', 'best+fractional'): (269, 1286),
    ('mkp 50x10', 'depth+pseudo'): (265, 1250),
    ('mkp 50x10', 'whole-cut off'): (355, 1684),
    ('mkp 50x10', 'no rounding'): (592, 1932),
    ('mkp 50x10', 'far child'): (284, 1467),
    ('general int 20x20', 'default'): (2667, 11820),
    ('general int 20x20', 'depth+fractional'): (22316, 132794),
    ('general int 20x20', 'best+fractional'): (13637, 70634),
    ('general int 20x20', 'depth+pseudo'): (3067, 18486),
    ('general int 20x20', 'whole-cut off'): (2728, 12156),
    ('general int 20x20', 'no rounding'): (2667, 11820),
    ('general int 20x20', 'far child'): (1625, 8763),
    ('bin packing 8/4', 'default'): (156, 363),
    ('bin packing 8/4', 'depth+fractional'): (80, 332),
    ('bin packing 8/4', 'best+fractional'): (79, 299),
    ('bin packing 8/4', 'depth+pseudo'): (25, 70),
    ('bin packing 8/4', 'whole-cut off'): (725, 2042),
    ('bin packing 8/4', 'no rounding'): (156, 363),
    ('bin packing 8/4', 'far child'): (18, 70),
    ('knapsack 100', 'default'): (1118, 1113),
    ('knapsack 100', 'depth+fractional'): (2326, 2243),
    ('knapsack 100', 'best+fractional'): (1118, 1113),
    ('knapsack 100', 'depth+pseudo'): (2326, 2243),
    ('knapsack 100', 'whole-cut off'): (3176, 3167),
    ('knapsack 100', 'no rounding'): (1118, 1113),
    ('knapsack 100', 'far child'): (188, 188),
    ('set cover 120x200', 'default'): (4, 128),
    ('set cover 120x200', 'depth+fractional'): (40, 691),
    ('set cover 120x200', 'best+fractional'): (12, 190),
    ('set cover 120x200', 'depth+pseudo'): (4, 128),
    ('set cover 120x200', 'whole-cut off'): (7, 203),
    ('set cover 120x200', 'no rounding'): (4, 128),
    ('set cover 120x200', 'far child'): (16, 278),
    ('mixed 30x40', 'default'): (424, 2410),
    ('mixed 30x40', 'depth+fractional'): (1059, 6806),
    ('mixed 30x40', 'best+fractional'): (685, 3812),
    ('mixed 30x40', 'depth+pseudo'): (651, 4860),
    ('mixed 30x40', 'whole-cut off'): (424, 2410),
    ('mixed 30x40', 'no rounding'): (424, 2410),
    ('mixed 30x40', 'far child'): (1039, 6244),
}

# The sparse engine's table (docs/design.md 19.6): SOLVE_METHOD=sparse selects it; SOLVE_METHOD=dense or unset selects the dense one (the default of this gate runs `--method dense`
# explicitly, since `auto` may pick either engine). Recorded with `SOLVE_METHOD=sparse --print` once the engine exists; an empty table fails the gate.
EXACT_SPARSE = {
    ('mkp 50x10', 'default'): (263, 1287),
    ('mkp 50x10', 'depth+fractional'): (269, 1286),
    ('mkp 50x10', 'best+fractional'): (269, 1286),
    ('mkp 50x10', 'depth+pseudo'): (265, 1250),
    ('mkp 50x10', 'whole-cut off'): (355, 1684),
    ('mkp 50x10', 'no rounding'): (592, 1932),
    ('mkp 50x10', 'far child'): (284, 1467),
    ('general int 20x20', 'default'): (1829, 9058),
    ('general int 20x20', 'depth+fractional'): (22485, 133883),
    ('general int 20x20', 'best+fractional'): (13563, 70551),
    ('general int 20x20', 'depth+pseudo'): (3118, 18961),
    ('general int 20x20', 'whole-cut off'): (1903, 9542),
    ('general int 20x20', 'no rounding'): (1829, 9058),
    ('general int 20x20', 'far child'): (1786, 9602),
    ('bin packing 8/4', 'default'): (10, 34),
    ('bin packing 8/4', 'depth+fractional'): (33, 128),
    ('bin packing 8/4', 'best+fractional'): (5, 28),
    ('bin packing 8/4', 'depth+pseudo'): (74, 233),
    ('bin packing 8/4', 'whole-cut off'): (503, 1529),
    ('bin packing 8/4', 'no rounding'): (167, 389),
    ('bin packing 8/4', 'far child'): (2, 23),
    ('knapsack 100', 'default'): (1118, 1113),
    ('knapsack 100', 'depth+fractional'): (2326, 2243),
    ('knapsack 100', 'best+fractional'): (1118, 1113),
    ('knapsack 100', 'depth+pseudo'): (2326, 2243),
    ('knapsack 100', 'whole-cut off'): (3186, 3177),
    ('knapsack 100', 'no rounding'): (1118, 1113),
    ('knapsack 100', 'far child'): (184, 184),
    ('set cover 120x200', 'default'): (4, 121),
    ('set cover 120x200', 'depth+fractional'): (4, 121),
    ('set cover 120x200', 'best+fractional'): (4, 121),
    ('set cover 120x200', 'depth+pseudo'): (4, 121),
    ('set cover 120x200', 'whole-cut off'): (11, 243),
    ('set cover 120x200', 'no rounding'): (4, 121),
    ('set cover 120x200', 'far child'): (15, 277),
    ('mixed 30x40', 'default'): (424, 2410),
    ('mixed 30x40', 'depth+fractional'): (1059, 6809),
    ('mixed 30x40', 'best+fractional'): (686, 3818),
    ('mixed 30x40', 'depth+pseudo'): (651, 4860),
    ('mixed 30x40', 'whole-cut off'): (424, 2410),
    ('mixed 30x40', 'no rounding'): (424, 2410),
    ('mixed 30x40', 'far child'): (1039, 6244),
}
METHOD = os.environ.get("SOLVE_METHOD", "dense")
os.environ["SOLVE_METHOD"] = METHOD
EXACT = EXACT_SPARSE if METHOD == "sparse" else EXACT_DENSE

bad = 0
if not EXACT and "--print" not in sys.argv:
    bad += 1
    print("FAIL: no counts are recorded for the sparse engine")
for (iname, cname), (nodes, iters) in (EXACT_DENSE if "--print" in sys.argv else EXACT).items():
    p, _ = run_solve(SOLVE, ["run"] + CFGS[cname], INSTS[iname])
    r = json.loads(p.stdout)
    got = (r["stats"]["nodes"], r["stats"]["iterations"])
    if "--print" in sys.argv:
        print(f"    ({iname!r}, {cname!r}): {got},")
    elif r["status"] != "optimal" or got != (nodes, iters):
        bad += 1
        print(f"FAIL {iname} / {cname}: {got[0]} nodes {got[1]} iterations, exactly {nodes} and {iters} expected (status {r['status']})")
print(f"node gate: {'FAILED' if bad else 'passed'} ({len(EXACT)} instance/option pairs, {bad} failures)")
sys.exit(1 if bad else 0)
