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

**Status: S2.** The language (params, one- and two-dimensional variables, `sum`, `forall`, constant folding), `check`, `expand`, `run` (a dense dual simplex with the bound-flipping ratio test and dual steepest-edge pricing: LP, and the relaxation of a MIP with `--relax`), `introspect` and `skill` are built. It agrees with HiGHS on 168 test LPs and, on the generated families of `scripts/bench_highs.py` (up to 800 rows, one machine, HiGHS through scipy), takes about as long as HiGHS's dual simplex, at 0.5x to 1.4x, and against OR-Tools' GLOP and CLP between 0.4x and 3.3x: faster on dense and knapsack LPs, 1.6x to 3.3x slower than CLP on transportation and assignment (`docs/design.md` sections 15, 17 and 18). The dense tableau limits the size (32 million cells); the sparse revised dual simplex (`solve run --method dense|sparse|auto`, default `auto`: sparse at 4% density or less) has no such limit, is 0.4x to 1.5x CLP's time on transportation and assignment and slower than the tableau on dense LPs (`docs/design.md` section 18.4). **S3 (MIP):** `solve run` on a model with `bool`/`int` variables solves it by branch and bound over the same simplex (warm-started children, plunging, best-bound or depth-first selection, most-fractional or pseudo-cost branching, node and iteration limits, `bound` and `gap` when a limit stops it), checked against HiGHS and OR-Tools; see `docs/design.md` section 19 for the design and the measured comparison. `--method dense|sparse|auto` also chooses the LP engine of the search (19.6): the sparse revised simplex lets a MIP exceed the 32M-cell tableau, and is slower than the tableau on small dense models. CP is S5.
`docs/design.md` says what is claimed, how it is measured and what is open.

```
cancho build --bin solve              # or: cancho build lib/model/*.cho tools/solve/*.cho --std -o build/solve
python3 scripts/check_language.py     # gate 1: tests/ok accepted, tests/refused refused with the named rule
python3 scripts/check_expand.py       # gate 2: solve expand equals the hand-derived tests/expand/*.json
python3 scripts/check_cli.py          # gate 3: no input reaches a panic
python3 scripts/check_highs.py        # gate 4: agrees with HiGHS (needs scipy)
python3 scripts/check_iterations.py    # gate 5: iteration counts (the pricing and the long step; docs/design.md section 17)
# note: the scripts' headers number the sparse gates 6 and 7 (design.md section 18) and the MIP gates 6 and 7 (section 19); the two were written in parallel and the numbers clash
python3 scripts/check_sparse.py        # sparse linear algebra against scipy splu (builds on `cancho build --bin sparsetest`; design.md 18.3.1)
python3 scripts/check_dense_vs_sparse.py # the dense solver as second oracle of the sparse one (design.md 18.3.2)
python3 scripts/check_mip.py --ortools # integer models against HiGHS MILP, enumeration, CP-SAT and SCIP (design.md 19.2)
python3 scripts/check_nodes.py        # exact node and iteration counts of the search (design.md 19.2); SOLVE_METHOD=sparse for the sparse engine's table (19.6)
python3 scripts/check_mip_engines.py  # the dense and the sparse LP engine of the search agree (design.md 19.6)
python3 scripts/check_cuts.py          # implied cuts through variable upper bounds never change an answer (design.md 19.8; needs scipy)
CANCHO=... python3 scripts/mutants_cuts.py # deliberate changes to the cut code; every one must be killed or explained (design.md 19.8)
python3 scripts/check_verify.py       # `solve verify` accepts what is feasible and refuses faults with the right tag (design.md section 20; needs scipy)
CANCHO=... python3 scripts/mutants_verify.py # deliberate changes to the verifier; every one must be killed or explained (design.md 20.6)
python3 scripts/bench_highs.py        # time against HiGHS: docs/design.md sections 15 and 17
CANCHO=... python3 scripts/mutants.py # deliberate changes to the checker; every one must be killed
python3 scripts/gen_layout.py --check # lib/model/layout.cho is what the generator prints
SOLVE=build/solve python3 scripts/site.py --check # docs/index.html, examples.html, stories.html are what the built binary prints today (python3 scripts/site.py writes them)
python3 scripts/bench_scaling.py     # the EV-depot model grown, against HiGHS and OR-Tools; writes docs/bench/scaling.* (design.md section 21; needs ortools and scipy)
```

**Verifying a solution (`docs/design.md` section 20).** `solve verify` re-checks a claimed solution, from `solve run` or any other solver, without the search: bounds, integrality, every row and the objective, to a tolerance (`--tolerance`, default 1e-6). Standard input is the model, a line `---`, then the solution as JSON (`solve run`'s output as it stands, or `{"x":{"x[0]":1,...},"objective":5}`):

```
$ (cat model.sol; echo ---; solve run < model.sol) | solve verify
{"status":"verified","objective":13.0,"objective_checked":true,"tolerance":0.000001,"max_bound_violation":0.0,...,"proves":"feasibility and the objective value, not optimality"}
```

A claim that fails is a refusal (exit 2) whose rule tag (`solve.bound-violated`, `solve.not-integral`, `solve.row-violated`, `solve.objective-mismatch`; `solve.bad-solution`, `solve.missing-variable`, `solve.unknown-variable` for a malformed claim) names the first violation, with a `violations` list. It does not prove optimality.

Authority: the binary reads standard input and writes standard output and error; it reads no file and has no network. Licence EUPL-1.2, copyright Alpibru S.L.

**Sparse revised dual simplex (S2b, `docs/design.md` sections 18.3 to 18.4).** `solve run --method dense|sparse|auto` (default `auto`: the sparse method when the matrix is at most 4% full or the tableau would not fit, the dense tableau otherwise). The sparse method is an LU-factorised revised dual simplex with the same long step and steepest-edge pricing; on generated network LPs it is 2.5x to 3.7x faster per iteration than the tableau and 0.4x to 1.5x CLP's time on transportation and assignment, solves min-cost flows of 8,000 rows that the tableau refuses (1.5 s; CLP takes 0.11 s), and is 1.4x to 2.4x slower than the tableau on dense LPs. One machine, generated models only.

**Pages.** `docs/index.html` (the landing page), `docs/examples.html` (every command with its output) and `docs/stories.html` (a bakery, a courier van, a night rota, two depots, an overnight EV-depot charging schedule with fewer-charger what-ifs, a refusal, a verification, an early stop) are written by `scripts/site.py` from real runs of `build/solve` on `docs/examples/*.sol`; the figures of the stories are computed from `solve expand` and `solve run` of those files. They are styled like cancho-ml's pages (`docs/assets`). Nothing publishes them: GitHub Pages is not enabled for this repository.
