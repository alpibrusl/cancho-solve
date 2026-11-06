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
        "19.8 search": ["--experiment", "96"]}   # 96 = 32 (no pausing, no RINS) + 64 (no MIR cuts): the search before docs/design.md 22.1, whose counts are kept so that its effort-only mutants stay killed
INSTS = {"mkp 50x10": lpgen.mkp(7, 50, 10), "general int 20x20": lpgen.random_mip(7, 20, 20, 0.4, 1.0), "bin packing 8/4": lpgen.bin_packing_lite(7, 8, 4),
         "knapsack 100": lpgen.knapsack(7, 100), "set cover 120x200": lpgen.set_cover(7, 120, 200, 0.05), "mixed 30x40": lpgen.random_mip(7, 30, 40, 0.3, 0.5)}
EXACT_DENSE = {
    ('mkp 50x10', 'default'): (245, 1135),
    ('mkp 50x10', 'depth+fractional'): (253, 999),
    ('mkp 50x10', 'best+fractional'): (253, 1261),
    ('mkp 50x10', 'depth+pseudo'): (253, 952),
    ('mkp 50x10', 'whole-cut off'): (575, 3286),
    ('mkp 50x10', 'no rounding'): (685, 2853),
    ('mkp 50x10', 'far child'): (222, 1279),
    ('general int 20x20', 'default'): (1538, 7501),
    ('general int 20x20', 'depth+fractional'): (15603, 71469),
    ('general int 20x20', 'best+fractional'): (10272, 65904),
    ('general int 20x20', 'depth+pseudo'): (1813, 8348),
    ('general int 20x20', 'whole-cut off'): (1366, 7433),
    ('general int 20x20', 'no rounding'): (1337, 7817),
    ('general int 20x20', 'far child'): (5506, 31937),
    ('bin packing 8/4', 'default'): (21, 50),
    ('bin packing 8/4', 'depth+fractional'): (42, 127),
    ('bin packing 8/4', 'best+fractional'): (42, 127),
    ('bin packing 8/4', 'depth+pseudo'): (21, 50),
    ('bin packing 8/4', 'whole-cut off'): (301, 766),
    ('bin packing 8/4', 'no rounding'): (22, 51),
    ('bin packing 8/4', 'far child'): (10, 50),
    ('knapsack 100', 'default'): (490, 518),
    ('knapsack 100', 'depth+fractional'): (1672, 1204),
    ('knapsack 100', 'best+fractional'): (490, 518),
    ('knapsack 100', 'depth+pseudo'): (1672, 1204),
    ('knapsack 100', 'whole-cut off'): (1352, 1190),
    ('knapsack 100', 'no rounding'): (492, 506),
    ('knapsack 100', 'far child'): (65, 59),
    ('set cover 120x200', 'default'): (4, 138),
    ('set cover 120x200', 'depth+fractional'): (42, 687),
    ('set cover 120x200', 'best+fractional'): (15, 266),
    ('set cover 120x200', 'depth+pseudo'): (4, 138),
    ('set cover 120x200', 'whole-cut off'): (9, 226),
    ('set cover 120x200', 'no rounding'): (4, 138),
    ('set cover 120x200', 'far child'): (17, 348),
    ('mixed 30x40', 'default'): (631, 6162),
    ('mixed 30x40', 'depth+fractional'): (995, 7193),
    ('mixed 30x40', 'best+fractional'): (968, 7862),
    ('mixed 30x40', 'depth+pseudo'): (695, 5436),
    ('mixed 30x40', 'whole-cut off'): (631, 6162),
    ('mixed 30x40', 'no rounding'): (631, 6162),
    ('mixed 30x40', 'far child'): (1392, 16612),
    ('mkp 50x10', '19.8 search'): (245, 1135),
    ('general int 20x20', '19.8 search'): (1889, 9180),
    ('bin packing 8/4', '19.8 search'): (21, 50),
    ('knapsack 100', '19.8 search'): (625, 562),
    ('set cover 120x200', '19.8 search'): (4, 138),
    ('mixed 30x40', '19.8 search'): (403, 3079),
}

# The sparse engine's table (docs/design.md 19.6): SOLVE_METHOD=sparse selects it; SOLVE_METHOD=dense or unset selects the dense one (the default of this gate runs `--method dense`
# explicitly, since `auto` may pick either engine). Recorded with `SOLVE_METHOD=sparse --print` once the engine exists; an empty table fails the gate.
EXACT_SPARSE = {
    ('mkp 50x10', 'default'): (245, 1135),
    ('mkp 50x10', 'depth+fractional'): (253, 999),
    ('mkp 50x10', 'best+fractional'): (253, 1261),
    ('mkp 50x10', 'depth+pseudo'): (253, 952),
    ('mkp 50x10', 'whole-cut off'): (575, 3293),
    ('mkp 50x10', 'no rounding'): (685, 2837),
    ('mkp 50x10', 'far child'): (222, 1279),
    ('general int 20x20', 'default'): (1395, 7024),
    ('general int 20x20', 'depth+fractional'): (15794, 68804),
    ('general int 20x20', 'best+fractional'): (10961, 68245),
    ('general int 20x20', 'depth+pseudo'): (1904, 9617),
    ('general int 20x20', 'whole-cut off'): (1535, 8873),
    ('general int 20x20', 'no rounding'): (1557, 9487),
    ('general int 20x20', 'far child'): (1578, 8742),
    ('bin packing 8/4', 'default'): (86, 170),
    ('bin packing 8/4', 'depth+fractional'): (31, 95),
    ('bin packing 8/4', 'best+fractional'): (31, 95),
    ('bin packing 8/4', 'depth+pseudo'): (86, 170),
    ('bin packing 8/4', 'whole-cut off'): (301, 686),
    ('bin packing 8/4', 'no rounding'): (93, 187),
    ('bin packing 8/4', 'far child'): (2, 23),
    ('knapsack 100', 'default'): (490, 518),
    ('knapsack 100', 'depth+fractional'): (1672, 1203),
    ('knapsack 100', 'best+fractional'): (490, 518),
    ('knapsack 100', 'depth+pseudo'): (1672, 1203),
    ('knapsack 100', 'whole-cut off'): (1354, 1264),
    ('knapsack 100', 'no rounding'): (492, 506),
    ('knapsack 100', 'far child'): (64, 60),
    ('set cover 120x200', 'default'): (4, 128),
    ('set cover 120x200', 'depth+fractional'): (4, 128),
    ('set cover 120x200', 'best+fractional'): (4, 128),
    ('set cover 120x200', 'depth+pseudo'): (4, 128),
    ('set cover 120x200', 'whole-cut off'): (11, 266),
    ('set cover 120x200', 'no rounding'): (4, 128),
    ('set cover 120x200', 'far child'): (17, 366),
    ('mixed 30x40', 'default'): (631, 6161),
    ('mixed 30x40', 'depth+fractional'): (995, 7268),
    ('mixed 30x40', 'best+fractional'): (968, 7854),
    ('mixed 30x40', 'depth+pseudo'): (695, 5436),
    ('mixed 30x40', 'whole-cut off'): (631, 6161),
    ('mixed 30x40', 'no rounding'): (631, 6161),
    ('mixed 30x40', 'far child'): (1798, 18720),
    ('mkp 50x10', '19.8 search'): (245, 1135),
    ('general int 20x20', '19.8 search'): (1784, 8339),
    ('bin packing 8/4', '19.8 search'): (86, 170),
    ('knapsack 100', '19.8 search'): (625, 563),
    ('set cover 120x200', '19.8 search'): (4, 128),
    ('mixed 30x40', '19.8 search'): (403, 3079),
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
