#!/usr/bin/env python3
"""Gate 7 (docs/design.md section 19.2): the search is judged by the work it does. The oracle cannot see a worse branching rule, a weaker cut or a wrong node order (the optimum is
the same), so the node and iteration counts of fixed instances under every option are held exactly: the search is deterministic, and a deliberate change of a rule moves these
numbers on purpose and they are then re-measured (docs/design.md 19.5). `--print` prints the table to paste."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import lpgen
from hs import run_solve

SOLVE = os.environ.get("SOLVE", "build/solve")
CFGS = {"default": [], "pseudo": ["--branching", "pseudo"], "depth+fractional": ["--node-select", "depth", "--branching", "fractional"], "best+fractional": ["--branching", "fractional"],
        "depth+pseudo": ["--node-select", "depth", "--branching", "pseudo"], "depth+reliable": ["--node-select", "depth"],
        "whole-cut off": ["--experiment", "1"], "no rounding": ["--experiment", "2"], "far child": ["--experiment", "4"],
        "19.8 search": ["--experiment", "96"]}   # 96 = 32 (no pausing, no RINS) + 64 (no MIR cuts): the search before docs/design.md 22.1, whose counts are kept so that its effort-only mutants stay killed
# the branching is reliability branching unless a configuration says otherwise (design.md 22.8); "pseudo" is the rule before it
INSTS = {"mkp 50x10": lpgen.mkp(7, 50, 10), "general int 20x20": lpgen.random_mip(7, 20, 20, 0.4, 1.0), "bin packing 8/4": lpgen.bin_packing_lite(7, 8, 4),
         "knapsack 100": lpgen.knapsack(7, 100), "set cover 120x200": lpgen.set_cover(7, 120, 200, 0.05), "mixed 30x40": lpgen.random_mip(7, 30, 40, 0.3, 0.5)}
EXACT_DENSE = {
    ('mkp 50x10', 'default'): (185, 2387),
    ('mkp 50x10', 'pseudo'): (245, 1135),
    ('mkp 50x10', 'depth+fractional'): (253, 999),
    ('mkp 50x10', 'best+fractional'): (253, 1261),
    ('mkp 50x10', 'depth+pseudo'): (253, 952),
    ('mkp 50x10', 'depth+reliable'): (157, 1642),
    ('mkp 50x10', 'whole-cut off'): (263, 2979),
    ('mkp 50x10', 'no rounding'): (451, 6485),
    ('mkp 50x10', 'far child'): (211, 2868),
    ('mkp 50x10', '19.8 search'): (185, 2387),
    ('general int 20x20', 'default'): (1280, 8925),
    ('general int 20x20', 'pseudo'): (1571, 8036),
    ('general int 20x20', 'depth+fractional'): (15603, 71445),
    ('general int 20x20', 'best+fractional'): (8856, 61813),
    ('general int 20x20', 'depth+pseudo'): (1851, 8736),
    ('general int 20x20', 'depth+reliable'): (969, 7172),
    ('general int 20x20', 'whole-cut off'): (1263, 10902),
    ('general int 20x20', 'no rounding'): (1280, 8902),
    ('general int 20x20', 'far child'): (1021, 8241),
    ('general int 20x20', '19.8 search'): (1024, 5779),
    ('bin packing 8/4', 'default'): (4, 155),
    ('bin packing 8/4', 'pseudo'): (21, 50),
    ('bin packing 8/4', 'depth+fractional'): (42, 127),
    ('bin packing 8/4', 'best+fractional'): (42, 127),
    ('bin packing 8/4', 'depth+pseudo'): (21, 50),
    ('bin packing 8/4', 'depth+reliable'): (4, 155),
    ('bin packing 8/4', 'whole-cut off'): (23, 271),
    ('bin packing 8/4', 'no rounding'): (27, 424),
    ('bin packing 8/4', 'far child'): (11, 223),
    ('bin packing 8/4', '19.8 search'): (4, 155),
    ('knapsack 100', 'default'): (490, 1586),
    ('knapsack 100', 'pseudo'): (490, 461),
    ('knapsack 100', 'depth+fractional'): (1672, 1178),
    ('knapsack 100', 'best+fractional'): (490, 461),
    ('knapsack 100', 'depth+pseudo'): (1672, 1178),
    ('knapsack 100', 'depth+reliable'): (1672, 2354),
    ('knapsack 100', 'whole-cut off'): (1352, 2342),
    ('knapsack 100', 'no rounding'): (492, 1476),
    ('knapsack 100', 'far child'): (64, 218),
    ('knapsack 100', '19.8 search'): (625, 1878),
    ('set cover 120x200', 'default'): (12, 1911),
    ('set cover 120x200', 'pseudo'): (4, 138),
    ('set cover 120x200', 'depth+fractional'): (42, 687),
    ('set cover 120x200', 'best+fractional'): (15, 266),
    ('set cover 120x200', 'depth+pseudo'): (4, 138),
    ('set cover 120x200', 'depth+reliable'): (12, 1749),
    ('set cover 120x200', 'whole-cut off'): (13, 2066),
    ('set cover 120x200', 'no rounding'): (12, 1911),
    ('set cover 120x200', 'far child'): (19, 4431),
    ('set cover 120x200', '19.8 search'): (12, 1911),
    ('mixed 30x40', 'default'): (643, 10402),
    ('mixed 30x40', 'pseudo'): (631, 6235),
    ('mixed 30x40', 'depth+fractional'): (995, 7332),
    ('mixed 30x40', 'best+fractional'): (968, 7932),
    ('mixed 30x40', 'depth+pseudo'): (695, 5583),
    ('mixed 30x40', 'depth+reliable'): (575, 6302),
    ('mixed 30x40', 'whole-cut off'): (643, 10402),
    ('mixed 30x40', 'no rounding'): (643, 10402),
    ('mixed 30x40', 'far child'): (1234, 19154),
    ('mixed 30x40', '19.8 search'): (342, 4329),
}

# The sparse engine's table (docs/design.md 19.6): SOLVE_METHOD=sparse selects it; SOLVE_METHOD=dense or unset selects the dense one (the default of this gate runs `--method dense`
# explicitly, since `auto` may pick either engine). Recorded with `SOLVE_METHOD=sparse --print` once the engine exists; an empty table fails the gate.
EXACT_SPARSE = {
    ('mkp 50x10', 'default'): (185, 2387),
    ('mkp 50x10', 'pseudo'): (245, 1135),
    ('mkp 50x10', 'depth+fractional'): (253, 999),
    ('mkp 50x10', 'best+fractional'): (253, 1261),
    ('mkp 50x10', 'depth+pseudo'): (253, 952),
    ('mkp 50x10', 'depth+reliable'): (157, 1642),
    ('mkp 50x10', 'whole-cut off'): (263, 2979),
    ('mkp 50x10', 'no rounding'): (451, 6501),
    ('mkp 50x10', 'far child'): (211, 2868),
    ('mkp 50x10', '19.8 search'): (185, 2387),
    ('general int 20x20', 'default'): (799, 7380),
    ('general int 20x20', 'pseudo'): (1395, 7109),
    ('general int 20x20', 'depth+fractional'): (15794, 69003),
    ('general int 20x20', 'best+fractional'): (10112, 63921),
    ('general int 20x20', 'depth+pseudo'): (1904, 8993),
    ('general int 20x20', 'depth+reliable'): (949, 6902),
    ('general int 20x20', 'whole-cut off'): (839, 7603),
    ('general int 20x20', 'no rounding'): (799, 7400),
    ('general int 20x20', 'far child'): (1192, 7491),
    ('general int 20x20', '19.8 search'): (627, 4878),
    ('bin packing 8/4', 'default'): (29, 566),
    ('bin packing 8/4', 'pseudo'): (86, 170),
    ('bin packing 8/4', 'depth+fractional'): (31, 95),
    ('bin packing 8/4', 'best+fractional'): (31, 95),
    ('bin packing 8/4', 'depth+pseudo'): (86, 170),
    ('bin packing 8/4', 'depth+reliable'): (29, 566),
    ('bin packing 8/4', 'whole-cut off'): (33, 576),
    ('bin packing 8/4', 'no rounding'): (29, 566),
    ('bin packing 8/4', 'far child'): (29, 387),
    ('bin packing 8/4', '19.8 search'): (29, 566),
    ('knapsack 100', 'default'): (490, 1586),
    ('knapsack 100', 'pseudo'): (490, 461),
    ('knapsack 100', 'depth+fractional'): (1672, 1177),
    ('knapsack 100', 'best+fractional'): (490, 461),
    ('knapsack 100', 'depth+pseudo'): (1672, 1177),
    ('knapsack 100', 'depth+reliable'): (1672, 2352),
    ('knapsack 100', 'whole-cut off'): (1354, 2344),
    ('knapsack 100', 'no rounding'): (492, 1498),
    ('knapsack 100', 'far child'): (64, 220),
    ('knapsack 100', '19.8 search'): (625, 1878),
    ('set cover 120x200', 'default'): (7, 1497),
    ('set cover 120x200', 'pseudo'): (4, 128),
    ('set cover 120x200', 'depth+fractional'): (4, 128),
    ('set cover 120x200', 'best+fractional'): (4, 128),
    ('set cover 120x200', 'depth+pseudo'): (4, 128),
    ('set cover 120x200', 'depth+reliable'): (9, 1508),
    ('set cover 120x200', 'whole-cut off'): (8, 1526),
    ('set cover 120x200', 'no rounding'): (7, 1497),
    ('set cover 120x200', 'far child'): (12, 2915),
    ('set cover 120x200', '19.8 search'): (7, 1497),
    ('mixed 30x40', 'default'): (643, 10419),
    ('mixed 30x40', 'pseudo'): (631, 6235),
    ('mixed 30x40', 'depth+fractional'): (995, 7389),
    ('mixed 30x40', 'best+fractional'): (968, 7927),
    ('mixed 30x40', 'depth+pseudo'): (695, 5491),
    ('mixed 30x40', 'depth+reliable'): (575, 6310),
    ('mixed 30x40', 'whole-cut off'): (643, 10419),
    ('mixed 30x40', 'no rounding'): (643, 10419),
    ('mixed 30x40', 'far child'): (1251, 17226),
    ('mixed 30x40', '19.8 search'): (342, 4329),
}
METHOD = os.environ.get("SOLVE_METHOD", "dense")
os.environ["SOLVE_METHOD"] = METHOD
EXACT = EXACT_SPARSE if METHOD == "sparse" else EXACT_DENSE

bad = 0
if not EXACT and "--print" not in sys.argv:
    bad += 1
    print("FAIL: no counts are recorded for the sparse engine")
todo = ([((i, c), (0, 0)) for i in INSTS for c in CFGS] if "--print" in sys.argv else list(EXACT.items()))
for (iname, cname), (nodes, iters) in todo:
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
