#!/usr/bin/env python3
"""Reads scripts/sweep_22_19.tsv (made by scripts/sweep_gomory.sh) and prints the table of docs/design.md 22.19: per setting and per group (the 33 models, the 16 held out), the models proved, the nodes and seconds
over the models proved both ways, the largest root-time ratio against no Gomory, the root bounds higher and lower, and any proved optimum that differs. Usage: python3 scripts/sweep_summary.py [FILE]"""
import collections, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1] if len(sys.argv) > 1 else "scripts/sweep_22_19.tsv")]
D = collections.defaultdict(dict)
for m, sp, rb, rs, st, obj, nodes, sec, fb in rows:
    D[m][sp] = dict(rb=None if rb == "-" else float(rb), rs=float(rs), st=st, obj=obj, nodes=int(nodes), sec=float(sec))
S = ["none", "gomory", "gomory,gomory-nnz=1", "gomory,gomory-nnz=2", "gomory,gomory-nnz=4", "gomory,gomory-nnz=7"]
held = lambda m: int(m.split("s")[-1]) >= 101
for grp, name in ((lambda m: not held(m), "33 models"), (held, "16 held out")):
    ms = [m for m in D if grp(m)]
    print("==", name, len(ms))
    for sp in S:
        pr = [m for m in ms if D[m][sp]["st"] == "optimal"]
        both = [m for m in ms if D[m]["none"]["st"] == "optimal" and D[m][sp]["st"] == "optimal"]
        nn, ns = sum(D[m]["none"]["nodes"] for m in both), sum(D[m][sp]["nodes"] for m in both)
        tn, ts = sum(D[m]["none"]["sec"] for m in both), sum(D[m][sp]["sec"] for m in both)
        ratio = {m: D[m][sp]["rs"] / max(D[m]["none"]["rs"], 0.05) for m in ms}
        wr = max(ms, key=lambda m: ratio[m])
        bad = [m for m in both if abs(float(D[m]["none"]["obj"]) - float(D[m][sp]["obj"])) > 1e-6 * (1 + abs(float(D[m]["none"]["obj"])))]
        lift = sum(1 for m in ms if D[m][sp]["rb"] is not None and D[m]["none"]["rb"] is not None and D[m][sp]["rb"] > D[m]["none"]["rb"] + 1e-7)
        low = sum(1 for m in ms if D[m][sp]["rb"] is not None and D[m]["none"]["rb"] is not None and D[m][sp]["rb"] < D[m]["none"]["rb"] - 1e-7)
        print("%-22s proved %2d  both %2d  nodes %6d vs %6d  secs %6.1f vs %6.1f  worst root ratio %5.1f (%s)  root higher %2d lower %2d  differing optima %s" % (sp, len(pr), len(both), ns, nn, ts, tn, ratio[wr], wr, lift, low, bad))
