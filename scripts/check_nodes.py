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
        "whole-cut off": ["--experiment", "1"], "no rounding": ["--experiment", "2"], "far child": ["--experiment", "4"],
        "19.8 search": ["--experiment", "96"]}   # 96 = 32 (no pausing, no RINS) + 64 (no MIR cuts): the search before docs/design.md 21.2, whose counts are kept so that its effort-only mutants stay killed
INSTS = {"mkp 50x10": lpgen.mkp(7, 50, 10), "general int 20x20": lpgen.random_mip(7, 20, 20, 0.4, 1.0), "bin packing 8/4": lpgen.bin_packing_lite(7, 8, 4),
         "knapsack 100": lpgen.knapsack(7, 100), "set cover 120x200": lpgen.set_cover(7, 120, 200, 0.05), "mixed 30x40": lpgen.random_mip(7, 30, 40, 0.3, 0.5)}
EXACT_DENSE = {
    ('mkp 50x10', 'default'): (245, 1152),
    ('mkp 50x10', 'depth+fractional'): (253, 1200),
    ('mkp 50x10', 'best+fractional'): (253, 1200),
    ('mkp 50x10', 'depth+pseudo'): (253, 1153),
    ('mkp 50x10', 'whole-cut off'): (575, 3737),
    ('mkp 50x10', 'no rounding'): (685, 3027),
    ('mkp 50x10', 'far child'): (222, 1192),
    ('general int 20x20', 'default'): (1434, 9009),
    ('general int 20x20', 'depth+fractional'): (13887, 108357),
    ('general int 20x20', 'best+fractional'): (9646, 64130),
    ('general int 20x20', 'depth+pseudo'): (1929, 14832),
    ('general int 20x20', 'whole-cut off'): (1381, 9056),
    ('general int 20x20', 'no rounding'): (1321, 9355),
    ('general int 20x20', 'far child'): (3488, 28310),
    ('bin packing 8/4', 'default'): (21, 62),
    ('bin packing 8/4', 'depth+fractional'): (73, 316),
    ('bin packing 8/4', 'best+fractional'): (73, 316),
    ('bin packing 8/4', 'depth+pseudo'): (21, 62),
    ('bin packing 8/4', 'whole-cut off'): (611, 2755),
    ('bin packing 8/4', 'no rounding'): (25, 70),
    ('bin packing 8/4', 'far child'): (7, 47),
    ('knapsack 100', 'default'): (490, 530),
    ('knapsack 100', 'depth+fractional'): (1672, 1589),
    ('knapsack 100', 'best+fractional'): (490, 530),
    ('knapsack 100', 'depth+pseudo'): (1672, 1589),
    ('knapsack 100', 'whole-cut off'): (1354, 1236),
    ('knapsack 100', 'no rounding'): (492, 515),
    ('knapsack 100', 'far child'): (64, 61),
    ('set cover 120x200', 'default'): (4, 128),
    ('set cover 120x200', 'depth+fractional'): (40, 690),
    ('set cover 120x200', 'best+fractional'): (12, 193),
    ('set cover 120x200', 'depth+pseudo'): (4, 128),
    ('set cover 120x200', 'whole-cut off'): (9, 205),
    ('set cover 120x200', 'no rounding'): (4, 128),
    ('set cover 120x200', 'far child'): (16, 278),
    ('mixed 30x40', 'default'): (631, 4876),
    ('mixed 30x40', 'depth+fractional'): (995, 8105),
    ('mixed 30x40', 'best+fractional'): (966, 6606),
    ('mixed 30x40', 'depth+pseudo'): (695, 6461),
    ('mixed 30x40', 'whole-cut off'): (631, 4876),
    ('mixed 30x40', 'no rounding'): (631, 4876),
    ('mixed 30x40', 'far child'): (1392, 14207),
    ('mkp 50x10', '19.8 search'): (245, 1152),
    ('general int 20x20', '19.8 search'): (1728, 9067),
    ('bin packing 8/4', '19.8 search'): (21, 62),
    ('knapsack 100', '19.8 search'): (625, 567),
    ('set cover 120x200', '19.8 search'): (4, 128),
    ('mixed 30x40', '19.8 search'): (403, 2319),
}

# The sparse engine's table (docs/design.md 19.6): SOLVE_METHOD=sparse selects it; SOLVE_METHOD=dense or unset selects the dense one (the default of this gate runs `--method dense`
# explicitly, since `auto` may pick either engine). Recorded with `SOLVE_METHOD=sparse --print` once the engine exists; an empty table fails the gate.
EXACT_SPARSE = {
    ('mkp 50x10', 'default'): (245, 1152),
    ('mkp 50x10', 'depth+fractional'): (253, 1200),
    ('mkp 50x10', 'best+fractional'): (253, 1200),
    ('mkp 50x10', 'depth+pseudo'): (253, 1148),
    ('mkp 50x10', 'whole-cut off'): (575, 3739),
    ('mkp 50x10', 'no rounding'): (685, 3009),
    ('mkp 50x10', 'far child'): (222, 1192),
    ('general int 20x20', 'default'): (1395, 8370),
    ('general int 20x20', 'depth+fractional'): (15530, 120156),
    ('general int 20x20', 'best+fractional'): (10238, 67134),
    ('general int 20x20', 'depth+pseudo'): (1880, 13606),
    ('general int 20x20', 'whole-cut off'): (1535, 9998),
    ('general int 20x20', 'no rounding'): (1556, 10617),
    ('general int 20x20', 'far child'): (1575, 10716),
    ('bin packing 8/4', 'default'): (65, 217),
    ('bin packing 8/4', 'depth+fractional'): (29, 117),
    ('bin packing 8/4', 'best+fractional'): (29, 117),
    ('bin packing 8/4', 'depth+pseudo'): (65, 217),
    ('bin packing 8/4', 'whole-cut off'): (683, 2872),
    ('bin packing 8/4', 'no rounding'): (74, 233),
    ('bin packing 8/4', 'far child'): (2, 23),
    ('knapsack 100', 'default'): (490, 530),
    ('knapsack 100', 'depth+fractional'): (1672, 1589),
    ('knapsack 100', 'best+fractional'): (490, 530),
    ('knapsack 100', 'depth+pseudo'): (1672, 1589),
    ('knapsack 100', 'whole-cut off'): (1354, 1334),
    ('knapsack 100', 'no rounding'): (492, 515),
    ('knapsack 100', 'far child'): (64, 62),
    ('set cover 120x200', 'default'): (4, 116),
    ('set cover 120x200', 'depth+fractional'): (4, 116),
    ('set cover 120x200', 'best+fractional'): (4, 116),
    ('set cover 120x200', 'depth+pseudo'): (4, 116),
    ('set cover 120x200', 'whole-cut off'): (11, 222),
    ('set cover 120x200', 'no rounding'): (4, 116),
    ('set cover 120x200', 'far child'): (15, 277),
    ('mixed 30x40', 'default'): (631, 4878),
    ('mixed 30x40', 'depth+fractional'): (995, 8183),
    ('mixed 30x40', 'best+fractional'): (968, 6683),
    ('mixed 30x40', 'depth+pseudo'): (695, 6461),
    ('mixed 30x40', 'whole-cut off'): (631, 4878),
    ('mixed 30x40', 'no rounding'): (631, 4878),
    ('mixed 30x40', 'far child'): (1798, 16214),
    ('mkp 50x10', '19.8 search'): (245, 1152),
    ('general int 20x20', '19.8 search'): (1784, 8759),
    ('bin packing 8/4', '19.8 search'): (65, 217),
    ('knapsack 100', '19.8 search'): (625, 567),
    ('set cover 120x200', '19.8 search'): (4, 116),
    ('mixed 30x40', '19.8 search'): (403, 2319),
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
