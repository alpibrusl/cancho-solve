# cancho-solve

Linear, mixed-integer and (later) constraint models as an agent-first command line, in [cancho](https://github.com/alpibrusl/cancho): the part of OR-Tools an agent needs to *state a
problem and get a checked answer*. Built like its siblings [cancho-opt](https://github.com/alpibrusl/cancho-opt) (`opt`, continuous black-box minimisation),
[cancho-ml](https://github.com/alpibrusl/cancho-ml) and [cancho-stats](https://github.com/alpibrusl/cancho-stats): one binary, JSON on standard output, an error is data with a
stable rule tag.

A problem is stated in a small text language, `.sol`, checked before anything is solved (`docs/design.md` sections 2 and 12):

```
param n   = 4;
param w   = [12, 2, 1, 4];
param v   = [4, 2, 1, 10];
param cap = 15;

var x[0..n] : bool;

maximize total: sum i in 0..n: v[i] * x[i];

subject to
    capacity: sum i in 0..n: w[i] * x[i] <= cap;
```

```
$ build/solve check < knapsack.sol
{"status":"ok","class":"MIP","variables":4,"integer":4,"constraints":1,"nonzeros":4,"objective":"maximize"}
$ build/solve expand < knapsack.sol          # the flat model a solver reads
{"variables":[{"name":"x[0]","kind":"bool","lo":0.0,"hi":1.0}, ...],"objective":{...},"constraints":[{"name":"capacity","sense":"<=","rhs":15.0,"terms":[[0,12.0],...]}]}
```

**Status: S2.** The language (params, one- and two-dimensional variables, `sum`, `forall`, constant folding), `check`, `expand`, `run` (a dense dual simplex with the bound-flipping ratio test and dual steepest-edge pricing: LP, and the relaxation of a MIP with `--relax`), `introspect` and `skill` are built. It agrees with HiGHS on 168 test LPs and, on the generated families of `scripts/bench_highs.py` (up to 800 rows, one machine, HiGHS through scipy), takes about as long as HiGHS's dual simplex, at 0.5x to 1.4x, and against OR-Tools' GLOP and CLP between 0.4x and 3.3x: faster on dense and knapsack LPs, 1.6x to 3.3x slower than CLP on transportation and assignment (`docs/design.md` sections 15, 17 and 18). The dense tableau limits the size (32 million cells); sparse methods are not built. MIP is S3, CP S5.
`docs/design.md` says what is claimed, how it is measured and what is open.

```
cancho build --bin solve              # or: cancho build lib/model/*.cho tools/solve/*.cho --std -o build/solve
python3 scripts/check_language.py     # gate 1: tests/ok accepted, tests/refused refused with the named rule
python3 scripts/check_expand.py       # gate 2: solve expand equals the hand-derived tests/expand/*.json
python3 scripts/check_cli.py          # gate 3: no input reaches a panic
python3 scripts/check_highs.py        # gate 4: agrees with HiGHS (needs scipy)
python3 scripts/check_iterations.py    # gate 5: iteration counts (the pricing and the long step; docs/design.md section 17)
python3 scripts/bench_highs.py        # time against HiGHS: docs/design.md sections 15 and 17
CANCHO=... python3 scripts/mutants.py # deliberate changes to the checker; every one must be killed
python3 scripts/gen_layout.py --check # lib/model/layout.cho is what the generator prints
```

Authority: the binary reads standard input and writes standard output and error; it reads no file and has no network. Licence EUPL-1.2, copyright Alpibru S.L.

**Sparse revised dual simplex (S2b, `docs/design.md` sections 18.3 to 18.4).** `solve run --method dense|sparse|auto` (default `auto`: the sparse method when the matrix is at most 4% full or the tableau would not fit, the dense tableau otherwise). The sparse method is an LU-factorised revised dual simplex with the same long step and steepest-edge pricing; on generated network LPs it is 2.5x to 3.7x faster per iteration than the tableau and 0.4x to 1.5x CLP's time on transportation and assignment, solves min-cost flows of 8,000 rows that the tableau refuses (1.5 s; CLP takes 0.11 s), and is 1.4x to 2.4x slower than the tableau on dense LPs. One machine, generated models only.
