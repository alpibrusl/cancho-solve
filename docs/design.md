# cancho-solve — design (S0, S1 and S2 built) — DRAFT

Every claim below is **measured** (with the command that measures it), a **choice**, or **open**. Nothing is measured yet: no code exists when this is written.

## 1. Scope

Linear programming (LP), mixed-integer linear programming (MIP) and, later, constraint programming (CP) over integers, as an agent-first command line: the
part of OR-Tools (`pywraplp`/GLOP/CBC and CP-SAT) that a program or an agent needs to *state a problem and get a checked answer*.

**Not in scope:** nonlinear programming (that is [cancho-opt](https://github.com/alpibrusl/cancho-opt), which minimises a black-box function), vehicle routing
as a dedicated API, a GUI, a modelling API for other languages, distributed search.

| Verb | What it does | Milestone |
|---|---|---|
| `solve check` | reads a model on standard input; prints its class (LP, MIP), sizes and objective sense, or a refusal | **S1a, built** |
| `solve fmt` | prints the model in canonical form, text or `--json` | S1b |
| `solve run` | solves it | S2 (LP), S3 (MIP), S5 (CP) |
| `solve verify SOLUTION` | checks a given solution against the model on standard input; no search | S2 |
| `solve introspect`, `solve skill` | the command surface as data | S1b |

## 2. How a problem is stated (choice)

Three ways were weighed. The decision is **a small text language, `.sol`, with a canonical JSON form as its exchange format**.

| | Text language (`.sol`) | JSON model | A cancho program that builds the model |
|---|---|---|---|
| Linear expression | `3*x + 2*y <= 10` | `{"terms":[[3,"x"],[2,"y"]],"op":"<=","rhs":10}` | `add_le(m, 3*x + 2*y, 10)` — and cancho has no operator overloading, no closures, no traits, so this is `lin_add(lin_scale(x,3), …)` |
| Sums over data | `sum i in 0..n: w[i]*x[i]` | the generator writes every term out | a loop, with a linear value moved round it (`docs/porting.md` of cancho) |
| Name of a constraint, for an explanation | `subject to capacity: …` | a `"name"` field | a string argument |
| Check before running | a checker with rule tags and a source position | a schema check, positions are paths | the cancho compiler, which says nothing about the *model* |
| A model changes | edit text, run | regenerate | **recompile** |
| Written by an agent | one short file, readable in a diff | long, and the same coefficient is far from its variable | long, and refused for reasons that are not about the problem |
| Exchange with other tools | needs a printer | native | none |

* **Why a language and not only JSON.** The unit an agent writes and a human reviews is a *model*, and a model is a few lines of mathematics. In JSON a
  linear constraint is a list of pairs, and a mistake in it (a coefficient attached to the wrong variable) is invisible in a diff. A language also lets
  the checker refuse with a position: `solve.nonlinear 4:21 "x * y": a product of two variables`.
* **Why not cancho itself as the model language.** cancho is a systems language: values are linear, there are no closures and no operator overloading, and a model
  edit would cost a compile. The model language is a *separate* small language, checked by its own checker, exactly as cancho-gpu's `.chx` is a separate
  language for kernels, with its own rules and its own refusals — cancho is what the tool is written in, not what the user writes.
* **Why JSON as well.** A generator (a script, an agent, another cancho tool) should not have to print `.sol`. `solve fmt --json` and `solve run --json-model`
  are the same model; `solve fmt` converts both ways and the round trip is a gate (section 7).
* **Not LP/MPS files.** They are accepted by every solver and good for exchange (`solve import`, **open**, later), but they cannot say `all_different`,
  `cumulative` or `element`, they have no data section, and their names are limited. They are an import, not the surface.

### 2.1 The language (choice; the grammar is the contract, `docs/language.md` once S1 is built)

```
// knapsack.sol
param n   = 4;
param w   = [12, 2, 1, 4];
param v   = [4, 2, 1, 10];
param cap = 15;

var x[0..n] : bool;

maximize total: sum i in 0..n: v[i] * x[i];

subject to
    capacity: sum i in 0..n: w[i] * x[i] <= cap;
```

* **Declarations.** `param NAME = NUMBER | [NUMBER, ...];` Data is fixed at check time. `var NAME[RANGE...]? : bool | int LO..HI | real LO..HI;` An index
  range is `A..B`, half-open as in cancho. A variable without bounds is refused (`solve.unbounded-domain`): the bound is part of the claim, not a default.
* **Objective.** `minimize|maximize [NAME:] EXPR;` at most one. None means a feasibility problem (CP style).
* **Constraints.** `subject to [NAME:] EXPR (<=|>=|==) EXPR;`, `sum i in R: …` and `forall i in R: CONSTRAINT` expand at check time.
* **Linear means linear.** `EXPR` is a sum of terms `coefficient * variable` and constants, where a coefficient is any expression of params and numbers.
  A product of two variables is `solve.nonlinear`. A division by a variable is the same rule.
* **Numbers** are decimal literals; `1/3` in a param is an exact rational (section 4).
* **CP (S5, reserved now).** `all_different(x[i] for i in R)`, `cumulative(...)`, `element(...)`, and `A ==> B` for a reified linear constraint. The keywords are reserved in
  S1 so that a model written today keeps its meaning, and the checker refuses them with `solve.not-built` until they exist.

Everything past this list is **open**: piecewise-linear terms, SOS sets, indicator constraints, multiple objectives.

## 3. The model, in memory and on the wire (choice)

After `check`, a model is **flat**: variables `0..n`, each with a kind and bounds; constraints as sparse rows (`columns`, `coefficients`, `sense`, `rhs`, `name`); one
objective row; a source map from each row to the `.sol` position that produced it (so an explanation names a line, not a row number). In cancho this is a
set of parallel `[int]`/`[float]` slices in one region or `box_slice` — there are no records of slices (`[T]` has no size in a struct field).

The canonical JSON is the same flat model; it is what `solve fmt --json` prints and what a generator may send.

## 4. Numbers (choice, **open** on exactness)

* Coefficients and bounds are read as decimal literals and held as `float` (binary64) in S1–S3.
* **Open:** the LP could instead run over exact rationals (`std.bignum` exists). That would make "optimal" a proof and the answer independent of rounding, at a
  large cost in time; whether it is worth it is decided by a measurement in S2 against HiGHS (section 7), not assumed here.
* In S2 the answer is verified in exact arithmetic regardless (`solve verify` re-evaluates every row in rationals), so a wrong float answer is reported as
  `"verified": false` and never printed as optimal.

## 5. Result and exit codes (choice)

```
{"status":"optimal","objective":15,"bound":15,"x":{"x[0]":1,"x[1]":1,"x[2]":1,"x[3]":1},"stats":{"iterations":9,"nodes":1},"verified":true}
```

`status` is one of `optimal`, `infeasible`, `unbounded`, `feasible` (a limit was reached; `bound` and the gap say how far from a proof). Exit status **0** when the
status is a proof (`optimal`, `infeasible`, `unbounded`), **1** when a limit stopped the search (`feasible`, or `unknown`), **2** on a refusal. A refusal prints
nothing on standard output and, on standard error, `{"error":"solve.<rule>","message":"...","repair":"...","at":{"line":L,"col":C}}`.

## 6. Authority and limits (choice)

The model arrives on **standard input** (corrected from the first draft, which read a file named on the command line: a tool that reads a path chosen by the user
cannot narrow its filesystem capability to it, and a stdin tool needs none). The binary writes standard output and error. **Measured, S1a:** `cancho authority` lists `args`,
`err_write`, `heap`, `io_read`, `io_write` and says it never touches the filesystem, the network, signals, other programs or foreign code. It is not yet checked in CI. Limits are flags with defaults and a refusal when exceeded, never a silent truncation:
`--max-vars`, `--max-rows`, `--max-nonzeros`, `--time-limit`, `--node-limit`, `--iteration-limit`. The limits are **open** until a measurement sets them.

## 7. Gates (written before the code they judge; each can fail)

1. **Language.** `scripts/check_language.py`: every `.sol` file under `tests/ok/` is accepted and every file under `tests/refused/` is refused with the rule tag named in its
   first line (`//~ RULE solve.nonlinear`), the way cancho's own fixtures work.
2. **Round trip.** `solve fmt` is idempotent, and `fmt` then `fmt --json` then reading it back is the same flat model.
3. **No panic.** `scripts/check_cli.py` feeds truncated, mutated and random bytes to every verb; every outcome is a result or a refusal.
4. **Oracle (S2+).** `scripts/check_highs.py` generates random LPs and MIPs with a fixed seed, solves each with `highspy`, and requires equal status and objective to a stated tolerance
   (and, for MIP, the same status). `--mutants` applies deliberate changes to the solver (a flipped inequality, a dropped bound, a wrong ratio test) and every one must be killed.
5. **Independence.** `solve verify` and the Python checker share no code with the search.

## 8. The rule tags (grows with each milestone)

| Tag | Meaning |
|---|---|
| `solve.syntax` | the text is not in the grammar |
| `solve.undeclared` | a name that is not a param, variable or index |
| `solve.redeclared` | a name declared twice |
| `solve.unbounded-domain` | a variable without bounds |
| `solve.bad-bounds` | a lower bound above an upper bound, or a non-finite one |
| `solve.nonlinear` | a product or quotient of variables |
| `solve.bad-index` | an index outside its range, or a range with the wrong length |
| `solve.two-objectives` | more than one `minimize`/`maximize` |
| `solve.too-large` | a limit of section 6 is exceeded |
| `solve.not-built` | a reserved keyword that no milestone has built yet |
| `solve.io` | the model file cannot be read |

## 9. Milestones

| | What | Done when |
|---|---|---|
| S0 | this document, the repository | gate 1's corpus is written |
| S1a | lexer, parser and checker for `var`, one objective, linear constraints; `solve check` | gates 1 and 3 pass (**measured, below**) |
| S1b | `param`, indexed `var`, `sum`, `forall`; `expand`, `introspect`, `skill`; gate 2 | gates 1 to 3 pass and every mutant killed (**measured, section 13**) |
| S2 | LP: dense dual simplex, `run`; measured against HiGHS | gate 4 passes for LP, mutants killed or explained, the gap to HiGHS measured (**section 15**). `verify` and the exactness decision (section 4) are **not done** |
| S3 | MIP: branch and bound over the LP | gate 4 passes for MIP |
| S4 | the page and the stories, `llms.txt` | each number written from a real run |
| S5 | CP: a propagation and clause-learning core, the reserved globals | an OR-Tools CP-SAT oracle gate |

## 10. Open

* Exact rational LP versus float with exact verification (section 4).
* Whether CP shares the model with MIP or is a second back end behind the same language.
* `solve import` for LP/MPS files.
* The default limits (section 6).

## 11. What S1a settled, and what it did not

**Built:** `lib/model/check.cho` (782 lines) and `tools/solve/main.cho` (157): `var NAME : bool | int LO..HI | real LO..HI;`, one `minimize|maximize [label:] EXPR;`, and
`subject to [label:] EXPR (<=|>=|==) EXPR; ...` with parentheses, `*` by numbers, `/` by a nonzero number, decimal literals with exponents (correctly rounded: the digits are
gathered as an integer-valued float and divided once by a power of ten). Constraints are counted after moving everything to one side, so `x - x + y <= 3` has one nonzero.

**Measured** (`python3 scripts/check_language.py`, `scripts/check_cli.py`, on the compiler at `a49ea779`-dirty, `--ignore-compiler-rev`):

* Gate 1: 4 models accepted, 10 refused each with the tag in its `//~ RULE` line. The gate was shown able to fail by changing one expectation (it reported `wanted solve.syntax, got solve.nonlinear`).
* Gate 3: 1,539 runs (every corpus file cut every 3 bytes, 60 byte-mutations of each, 300 random inputs, 4,100 variables, 5,000 nested parentheses): every one a result or a refusal with a rule tag.
* `cancho fmt --check` passes.

**Known limits of S1a (corrections will be made here):**

* A parenthesised group that holds only numbers counts as a group, so `(1+2)*(x)` is refused as `solve.nonlinear`, which is wrong; the fix is constant folding in S1b.
* Bounds of an `int` variable are not checked to be integers.
* A constraint's two sides are not checked for being both constant (`1 <= 2;` is accepted).
* Mutants of the checker have **not** been run: the gate shows that the corpus detects one hand-made change, not that it kills every plausible one.
* The 4,096-variable limit is a constant, not a flag (section 6, open).
* Nothing is solved yet. The oracle gate (section 7, gate 4) does not exist.

## 12. S1b: data, indexed variables, `sum`, `forall`, `expand` (written before the code)

**Grammar added to section 2.1** (choices):

* `param NAME = EXPR;` and `param NAME = [EXPR, ...];` where `EXPR` is a constant expression: numbers, params, loop indices, `+ - * /`, parentheses, `sum`. Arrays are one-dimensional, 0-based.
* `var NAME[A..B]` and `var NAME[A..B, C..D] : KIND [LO..HI];` Ranges are half-open and may use params. Bounds may use params. Two dimensions at most. A bound of an `int` variable must be a whole number (`solve.bad-bounds` otherwise).
* `sum i in A..B: TERM` is a **term**, not an expression: its body is one term (factors joined by `*` and `/`), and `+` or `-` ends it. For a longer body, parenthesise: `sum i in R: (a[i]*x[i] + b[i])`. A sum may start a term anywhere an expression can, including the right side of a relation, and sums nest.
* `forall i in A..B [, j in C..D]: [label:] EXPR REL EXPR;` inside `subject to`. Nested `forall`s are allowed. A constraint's name becomes `label[i,j]` (up to four loop values are kept).
* Indices (`x[i+1]`, `w[i*n+j]`) are constant expressions that must evaluate to a whole number inside the declared range, or the model is refused `solve.bad-index`.
* A parenthesised group with no variable in it is a number: `(1+2)*x` is linear (fixes the S1a limit).
* A range, an index or a bound that contains a variable is `solve.not-constant`.
* Loop and iteration budget: all loops together may run at most 10,000,000 iterations (`solve.too-large`). **Choice**, open until measured.

**`solve expand`** replaces the `solve fmt` of section 1: the checker keeps no syntax tree, so what it can print canonically is the **expanded model** (section 3), as JSON:

```
{"variables":[{"name":"x[0]","kind":"bool","lo":0,"hi":1}, ...],
 "objective":{"sense":"maximize","name":"total","constant":0,"terms":[[0,4],[1,2]]},   // null when there is none
 "constraints":[{"name":"capacity","sense":"<=","rhs":15,"terms":[[0,12],[1,2]]}]}     // "name" omitted when unlabeled
```

A constraint is moved to the form `terms (<=|>=|==) rhs`: variables left, constants right. Terms are sorted by variable index, a term whose coefficients cancel is dropped. `check` and `expand` read the same model, so their counts agree (a gate).
Reading the JSON back in is S2's (`solve run --json`); the round-trip of section 7 gate 2 moves there. **Changed gate 2:** every file in `tests/expand/` has a hand-derived expected expansion, compared as numbers, not text.

**`solve introspect`** prints the verbs, the exit codes and the rule tags as JSON; **`solve skill`** prints the same as text for an agent. Both are generated from the tables the checker uses (the rule names), so a rule cannot be added without appearing in them.

**Limits (constants, open):** 16,384 scalar variables, 4,096 declared names, 16,384 rows, 1,048,576 nonzeros, 1,048,576 param values (names, nonzeros and param values were raised in S2 when benchmark instances were refused: 1,024, 262,144 and 65,536 before), loops nested 8 deep.

## 13. What S1b settled, and what it did not

**Built** (compiler `a49ea779`-dirty, `--ignore-compiler-rev`): `lib/model/{layout,lex,expr,stmt}.cho` and `tools/solve/{emit,main}.cho`, the largest file 498 lines. `layout.cho` is generated
(`scripts/gen_layout.py --check`). `cancho fmt --check` passes; `cancho authority` lists `args`, `err_write`, `heap`, `io_read`, `io_write` and no filesystem, network, signals, process or foreign code.

**Measured:**

* Gate 1 (`scripts/check_language.py`): 10 models accepted, 22 refused each with the tag in its `//~ RULE` line.
* Gate 2 (`scripts/check_expand.py`): 5 expansions equal their hand-derived files; `check` agrees with `expand` on the counts. Shown able to fail: changing one right-hand side in a golden file is reported.
* Gate 3 (`scripts/check_cli.py`): 3,288 runs (cuts, byte mutations, random bytes, 16,400 variables, 5,000 nested parentheses), every one a result or a tagged refusal.
* Mutants (`scripts/mutants.py`, 18): **18 killed**. The first run killed 13 and showed four gaps in the corpus (equal bounds, an empty declared range, and skipping the body of an empty `sum` or `forall`);
  `tests/ok/empty_loops.sol`, `tests/ok/equal_bounds.sol` and `tests/refused/empty_range.sol` were added and the five affected mutants (one had been aimed at the wrong file) were run again.
* Size: a 100 x 100 assignment (10,000 variables, 200 rows, 20,000 nonzeros) checks in 5 ms and expands to 860 KB in 18 ms, **one run, a debug build of the compiler, one machine**; not a benchmark.

**Known limits (corrections will be made here):**

* The body of a `forall` over an **empty range is skipped without being read**, so a syntax error inside it is not reported (`tests/ok/empty_loops.sol` relies on this for the body's out-of-range index; the same holds for an empty `sum`).
* Row names keep at most four loop values.
* A `sum` is a term: `sum i in R: a[i]*x[i] + 3` is the sum **plus 3**, and `x * sum ...` is refused. Parenthesise to change either.
* The checker never evaluates a model; nothing is solved. Gate 4 (the HiGHS oracle) does not exist, and the iteration budget, the size limits and the 10,000,000-step loop budget are constants, not measured defaults.

## 14. S2: linear programming (written before the code)

**Algorithm (choice): a dense, bounded-variable dual simplex.** Every variable of a `.sol` model is bounded (section 2.1), so:

* the slack basis is dual feasible from the start: each structural variable is placed at the bound its cost prefers (lower when the minimised cost is >= 0, upper otherwise), with no phase 1;
* the problem cannot be unbounded, so `unbounded` is not an outcome of `run` (it stays in section 5 for later column types);
* the loop is: pick the basic variable that violates a bound most, send it to that bound, enter the nonbasic variable of the minimum dual ratio |d_j / alpha_rj| (ties: the larger |alpha_rj|, then the smaller index). A row with no eligible column proves the model infeasible.

The tableau is dense (m x (n + m) floats, one row for each constraint and one column for each variable and each row's logical variable), stored row-major on the heap. Each pivot costs O(m (n + m)). **This is a first solver, chosen for being short and checkable, not for speed**: it has no presolve, no sparse factorisation, no bound flipping, no scaling, no refactorisation (error accumulates), no perturbation against cycling (an iteration limit stops it instead).
It refuses a model whose tableau would exceed 32,000,000 cells (`solve.too-large`; a **choice**, open).

**`solve run [--relax] [--iteration-limit N]`.** A model with integer or boolean variables is refused (`solve.not-built`, "needs S3") unless `--relax` is given, which solves the relaxation. Output (section 5): `status` (`optimal`, `infeasible`, `unknown` when the iteration limit stopped it: a dual simplex holds no feasible point until it finishes), `objective` in the model's own sense with its constant, `x` as an object keyed by variable name, `stats` (`iterations`, `rows`, `columns`), and `verified`/`max_violation`: the largest violation of a bound or a row by the printed `x`, computed by code that reads the expanded model and not the simplex's tableau. `verified` is true when that is at most 1e-6 (scaled by 1 + |bound|, **a choice**). The exact rational check of section 4 is **not built**; what is checked is a floating-point residual, and that is what the field is called.

**Gate 4 (written before the solver): `scripts/check_highs.py`.** Fixed-seed random LPs (boxed variables, rows of the three senses, some made infeasible on purpose) are written as `.sol`, solved by `solve run` and by HiGHS through `scipy.optimize.linprog(method="highs")` (the HiGHS bundled with scipy; **the Python environment has scipy 1.17.1 and neither `highspy` nor OR-Tools**), and must agree on status and, when optimal, on the objective to 1e-6 relative; and the printed `x` must satisfy the expanded model when re-evaluated in Python. The instance given to HiGHS is built from `solve expand`, so both solvers see the same numbers.

**Benchmark (written before the solver): `scripts/bench_highs.py`.** The same instances (random dense LP; transportation; the assignment LP, which is highly degenerate; the multi-dimensional knapsack relaxation) at growing sizes, each solved by `solve run --relax` (wall clock of the whole process, which includes reading and expanding the model) and by HiGHS (wall clock of the `linprog` call only, with `highs-ds` the dual simplex and `highs-ipm` the interior point, so the comparison is made against the same algorithm and against the default best). Minimum of 5 runs; the machine, the versions and the load are printed with the table. Nothing is claimed about speed before this has been run, and what it shows is written in section 15 whatever it is. **OR-Tools is not installed here and is not compared**; installing it needs the network, which is the maintainer's call.

**Mutants:** deliberate changes to the simplex (a flipped sign of a ratio, a wrong bound, a missing update of the reduced costs, a skipped infeasibility proof, a changed tolerance) are run against gate 4; every one must be killed.

## 15. What S2 settled: the gap to HiGHS (measured)

**Built:** `lib/lp/simplex.cho` (the dense dual simplex of section 14), `run` in `tools/solve/{emit,main}.cho`; `scripts/lpgen.py`, `scripts/hs.py`, `scripts/check_highs.py`, `scripts/bench_highs.py`.
`cancho fmt --check` passes; `cancho authority` still lists only `args`, `err_write`, `heap`, `io_read`, `io_write`. The largest source file is under 800 lines.

**Gates.** Gate 4 (`scripts/check_highs.py`): 168 fixed-seed instances (120 small random, 30 medium random, 6 transportation, 6 assignment relaxations, 6 multi-knapsack relaxations): 145 optimal and 23 infeasible, **HiGHS and `solve run --relax` agree on all of them** (status; objective to 1e-6 relative; the printed solution re-checked against the expanded model in Python; the printed objective equals the objective of the printed solution). Gate 3 now also covers `run --relax` on cuts and mutations of the small models and the iteration limit (4,578 runs).

**Mutants (34 in all).** The 18 of the checker are all killed (section 13). Of the 16 aimed at the simplex and `run`, **15 are killed and 1 survives: "`verified` is always true"** (`tools/solve/emit.cho`). It survives because `verified` is false only when the simplex returns a point that violates the model, and the oracle gate would already have failed on such a point; killing the mutant needs a way to inject a wrong solution, which is not built. It is an explained survivor, not a pass.
(Two of the mutants had to be corrected before they ran: one named text that `cancho fmt` had since rewritten, and the run was repeated for it.)

**The comparison.** `python3 scripts/bench_highs.py --runs 3 --max-seconds 60`, one seed (7) for each size, on the same machine and run in one session with nothing else running: macOS 26.2, arm64 (Apple Silicon), Python 3.14.5, scipy 1.17.1 (the HiGHS it bundles, through `scipy.optimize.linprog`, with `highs-ds` the dual simplex and `highs` the default choice). Ours is built by a debug build of the cancho compiler with its default (Cranelift) code generator. "ours - floor" is the wall clock of `solve run --relax` minus that of `solve check` on the same model, each the minimum of 3 (start-up, reading and expansion removed); HiGHS is the wall clock of the `linprog` call alone. Both include their own fixed overheads, so **ratios at the small sizes (under about 5 ms) are not meaningful**: scipy's call overhead is about half a millisecond. The answers agree on every row (objective to 1e-6 relative).

| family | size | rows | cols | our iters | HiGHS iters | ours - floor (s) | HiGHS dual (s) | HiGHS default (s) | ours / dual | ours / default |
|---|---|---|---|---|---|---|---|---|---|---|
| random dense LP | 20x40 | 20 | 40 | 16 | 9 | 0.0005 | 0.0006 | 0.0005 | 0.9 | 1.0 |
| random dense LP | 50x100 | 50 | 100 | 136 | 40 | 0.0008 | 0.0014 | 0.0012 | 0.6 | 0.6 |
| random dense LP | 100x200 | 100 | 200 | 684 | 136 | 0.0125 | 0.0061 | 0.0057 | 2.0 | 2.2 |
| random dense LP | 200x400 | 200 | 400 | 2213 | 310 | 0.1533 | 0.0258 | 0.0250 | 5.9 | 6.1 |
| random dense LP | 400x800 | 400 | 800 | 9020 | 1118 | 2.3880 | 0.2822 | 0.2896 | 8.5 | 8.2 |
| random dense LP | 800x1600 | 800 | 1600 | 43028 | 2851 | 47.2773 | 3.5957 | 3.5326 | 13.1 | 13.4 |
| transportation | 10x20 | 30 | 200 | 24 | 23 | 0.0002 | 0.0009 | 0.0008 | 0.2 | 0.3 |
| transportation | 40x80 | 120 | 3200 | 117 | 115 | 0.0027 | 0.0072 | 0.0066 | 0.4 | 0.4 |
| transportation | 60x120 | 180 | 7200 | 213 | 189 | 0.0145 | 0.0164 | 0.0158 | 0.9 | 0.9 |
| transportation | 80x160 | 240 | 12800 | 355 | 292 | 0.0375 | 0.0326 | 0.0322 | 1.1 | 1.2 |
| transportation | 100x160 | 260 | 16000 | 369 | 260 | 0.0515 | 0.0418 | 0.0372 | 1.2 | 1.4 |
| assignment (LP relaxation) | 20x20 | 40 | 400 | 44 | 36 | 0.0001 | 0.0015 | 0.0012 | 0.1 | 0.1 |
| assignment (LP relaxation) | 40x40 | 80 | 1600 | 116 | 87 | 0.0023 | 0.0040 | 0.0038 | 0.6 | 0.6 |
| assignment (LP relaxation) | 60x60 | 120 | 3600 | 229 | 143 | 0.0093 | 0.0089 | 0.0092 | 1.1 | 1.0 |
| assignment (LP relaxation) | 80x80 | 160 | 6400 | 251 | 207 | 0.0123 | 0.0179 | 0.0176 | 0.7 | 0.7 |
| assignment (LP relaxation) | 100x100 | 200 | 10000 | 393 | 257 | 0.0374 | 0.0285 | 0.0285 | 1.3 | 1.3 |
| multi-knapsack (relaxation) | 100 items, 10 rows | 10 | 100 | 146 | 22 | 0.0001 | 0.0010 | 0.0007 | 0.1 | 0.1 |
| multi-knapsack (relaxation) | 500 items, 30 rows | 30 | 500 | 1528 | 75 | 0.0191 | 0.0049 | 0.0046 | 3.9 | 4.1 |
| multi-knapsack (relaxation) | 1000 items, 50 rows | 50 | 1000 | 4902 | 126 | 0.1726 | 0.0153 | 0.0151 | 11.3 | 11.5 |
| multi-knapsack (relaxation) | 2000 items, 100 rows | 100 | 2000 | 21917 | 258 | 2.7096 | 0.0673 | 0.0675 | 40.3 | 40.2 |
| multi-knapsack (relaxation) | 4000 items, 200 rows | 200 | 4000 | 94644 | 471 | 45.4193 | 0.3184 | 0.3191 | 142.6 | 142.3 |

What it shows, and nothing past it:

* **On network-structured LPs we are at parity.** Transportation and assignment relaxations, up to 16,000 columns, are 0.4 to 1.4 times HiGHS's time, with a comparable number of iterations (369 against 260 at the largest). Each row is a few nonzeros and the tableau fills slowly.
* **On general dense LPs we are 2x to 13x slower and the gap grows with size** (2.0x at 100 x 200, 8.5x at 400 x 800, 13.1x at 800 x 1600: 47 s against 3.6 s). The time for one iteration is about the same as HiGHS's (1.1 ms against 1.3 ms at 800 x 1600; 47.3 s / 43,028 and 3.60 s / 2,851), **so the gap is the number of iterations**: 15 times as many.
* **On the multi-knapsack relaxation, a boxed problem with few rows and many columns, the gap is 4x, 11x, 40x and 143x as the size grows** (1000 items: 11x; 4000 items: 45.4 s against 0.32 s), and our iteration count is 200 times HiGHS's at the largest (94,644 against 471).
* **Why (a hypothesis, not yet measured by changing the solver):** our pricing is the largest infeasibility with no bound flipping, on a model in which every variable is boxed, so an iteration that HiGHS spends passing over several bounds at once costs us several iterations. HiGHS also presolves, uses dual steepest-edge pricing and a sparse factorisation. Section 16 measures the per-iteration side (it is at C speed, so the gap is not the code generator); which of the algorithmic differences the iteration gap is made of is **open**; the next step is to add the bound-flipping ratio test and then dual steepest-edge pricing, each on its own, and measure again.
* **LLVM backend:** on the 400 x 800 instance `--backend llvm` took 2.53 s against 2.62 s with the default (one instance, minimum of 3, an earlier build): the code generator is not what is slow.

**Not claimed.** OR-Tools (GLOP, PDLP) and a commercial solver are **not** compared: neither is installed here and installing needs the network. One machine, one seed for each size, three runs. The instances are random or textbook families, not a public benchmark library (netlib, MIPLIB); an LP from a real application may behave differently. Nothing is said about MIP (S3).

**Limits found while measuring (corrections made in section 12):** names, nonzeros and param values were raised after benchmark instances were refused (section 12's limit paragraph says the old values). The dense tableau refuses a model over 32,000,000 cells. 16,384 variables is still the cap (a 100 x 200 transportation has 20,000 and is refused).

**Not done in S2:** `solve verify` as a verb (the field `verified` exists, as a floating-point residual of 1e-6; the exact rational check of section 4 is not built); degeneracy is handled only by an iteration limit; no refactorisation, so error accumulates in the tableau (the oracle shows no wrong answer on 168 instances, which is not a proof that none exists).

## 16. Profile: where the time goes, and whether cancho is the problem (measured)

**Question.** Section 15 found that our time for one iteration is close to HiGHS's and that we need 8 to 200 times as many iterations. Is the per-iteration time good, or only close because HiGHS spends its on other things, and does cancho's code generation cost anything?

**Methods, and what did not work.** A sampling profile did not give a usable answer: `sample` attributes everything to one symbol (the optimiser inlines the loops, and the binary has no frame pointers), `xctrace`'s Time Profiler returned stack-less samples for 99% of them, and sampling the program counter through lldb's Python API did not return control after the first stop. So the answer below comes from three measurements that do not need a sampler: (1) a counter of the pivot's row updates, added in a scratch copy of the solver (`stats[3]`, printed as `row_updates`; the counter is not in the repository); (2) the disassembly of the pivot's inner loop (`otool -tv build/solve`); (3) the loop alone, in cancho and in C (`bench/pivot.cho`, `bench/pivot.c`).

**Measured** (the same machine as section 15; times are the minimum of 3 to 5 runs of whole processes, which include about 5 ms of start-up):

1. **Essentially all the time is the pivot's row update.** The 400 x 800 random LP makes 9,020 iterations and on average **399 of its 400 rows are updated in each** (3,598,548 row updates of 1,200 cells: 4.32 x 10^9 cell updates); the 2000-item multi-knapsack relaxation updates 99 of 100 rows (4.56 x 10^9 cells). At the loop's rate measured alone at the same size (point 3: 0.64 to 0.74 ns for a cell update, with and without the start-up of the process taken out), 4.32 x 10^9 cells would take 2.8 to 3.2 s; the whole run takes 2.66 s. The prediction is within about 20% of the run, so the pivot is the run to the accuracy of this method; the other loops of an iteration (O(rows + columns) each) are inside that error and were not timed separately. **The tableau is dense after the first few pivots whatever the model looked like**, so the dense method does O(rows x columns) work every iteration however sparse the problem is. That is the cost of choosing a dense tableau (section 14), and it is the whole cost.
2. **The inner loop compiles to scalar code with a checked add and a bounds compare on each index** (`adds`/`b.vs`, `cmp`/`b.hs`, then `ldr`, `ldr`, `fmul`, `fsub`, `str`: 16 instructions for each cell, no fused multiply-add, no NEON). `docs/check-cost.md` and `docs/parallelism.md` predict this: a loop with a checked integer add or a loaded bound is not reordered or vectorised.
3. **It does not cost anything here.** The loop alone, 479,000 cell updates for each of 100 sweeps of a 400 x 1200 matrix (3.8 MB): cancho (LLVM, the default backend) in the three spellings of `bench/pivot.cho` (flat indices; row slices with a loop condition that proves both bounds; `wrapping_add`) takes **35.5 to 35.9 ms in all three**, C `clang -O2 -ffp-contract=off` takes **34.0 ms** (vectorised or not), the checksum agrees. With the working set in cache (a 60 x 200 matrix, 944 x 10^6 updates): cancho 0.298 to 0.301 s in all three, C 0.300 s vectorised and 0.300 s scalar. **cancho/LLVM equals C on this kernel, and the three spellings are interchangeable here**; the clang vectorised loop is no faster than the scalar one on this machine, so the scalar code is not what limits it. The checks cost nothing measurable on this kernel, and I found no gain from rewriting the indices.
4. **Cranelift is slower on the same loop**: at the solver's size 91 ms (variant `a`, 2.6 times LLVM's 35 ms), 58 ms (`c`) and 69 ms (`b`); in cache 1.41 s against 0.30 s (variant `a`, 4.7 times). `--backend cranelift` should not be used for numeric kernels.
5. **The cost of a cell update depends on the size of the tableau**: 0.32 ns when it fits in cache (96 KB), 0.64 to 0.74 ns at 3.8 MB (the loop alone). Memory traffic, not arithmetic, is the second order.

**What this says.** The per-iteration time of 274 microseconds at 400 x 800 is what a dense tableau costs on this machine at C speed, so the code generator is **not** where the gap to HiGHS comes from (on this kernel, this machine, with the default LLVM backend). The gap is (a) the number of iterations (section 15: 8x to 200x), and (b) HiGHS doing less work for each iteration on sparse problems (we update 99% of the rows whatever the sparsity; HiGHS's work on the 4000-item knapsack was 0.32 s for 471 iterations).

**Where to look next (not done; each is a change to the solver and needs its own measurement):**

1. **Fewer iterations:** the bound-flipping ratio test and dual steepest-edge pricing (section 15's hypothesis; the model is boxed throughout). **Done in section 17**: the iterations then matched HiGHS's within about ten percent on the dense and knapsack families and the gaps below closed to about parity on those instances. The figures of this section and of section 15 are the ones measured before that change.
2. **Less work per iteration:** a revised simplex with an LU factorisation that exploits sparsity, in place of the dense tableau. This is the larger change.
3. **Threads:** the row updates of one pivot are independent, and cancho has `spawn`/`join` with a one-pointer payload (`docs/parallelism.md`); not tried here. It would cut the 2.5 s by at most the number of cores, which does not change the iteration count.
4. **Tooling:** a way to profile cancho programs by function would have saved this section's detours (frame pointers or a symbol table that survives inlining); that is a finding about the compiler, not about this solver.

**Not claimed.** One machine (Apple Silicon, one core used); the kernel measured is the pivot loop only, not the rest of the iteration (the ratio test and the pricing loops are O(rows + columns) and were not timed separately: the counter and the loop's rate put the pivot at about all of the run); ARM64 only, so what the checks cost on x86-64 (SSE2 baseline, the machine of `docs/check-cost.md`) is not measured here.

**Which compiler (a correction).** The measurements above were first made with `cancho` built from the Rust workspace (`target/debug/cancho`, an older commit than the pin, on a branch that was not `main`). The Rust compiler is the legacy one; the compiler people run is the cancho-written one (`docs/standalone-cancho.md`). Re-checked on `main` at `5a5dd1f2`: `scripts/build-standalone.sh` built the standalone `cancho` (three stages, stage 2 equal to stage 3 byte for byte), `cancho build --bin solve` rebuilt `build/solve` with it, and the four gates pass. The 400x800 random LP (`--relax`, three runs, whole process) took 2.46, 2.58 and 2.65 s (2.66 s before); the 2,000-item multi-knapsack took 2.82, 2.68 and 2.54 s (2.38 s before). Same range, so the conclusions of this section stand. The pivot-loop microbenchmarks (`bench/`) and the Cranelift comparison were not re-run: Cranelift is a backend of the Rust compiler (`docs/standalone-cancho.md` §1 lists `--backend cranelift` as unavailable in the cancho-written command line; `build --bin solve --backend cranelift` with the standalone `cancho` was tried and answered `unknown option --bin`), so that comparison is of the legacy build only.

## 17. Fewer iterations: the bound-flipping ratio test (written before the code)

Section 16 found the gap to HiGHS is iteration count (8 to 200 times as many) and dense work per iteration. This section takes the first, in two steps; each is measured by the benchmark of section 15 (`scripts/bench_highs.py`, column "our iters") before the next is started.

**17.1 Bound flipping (the long-step ratio test).** Every variable here is boxed, and the ratio test of section 14 stops at the first breakpoint: the nearest nonbasic column whose reduced cost reaches zero. A boxed column may instead be *passed*: it is moved to its other bound, which keeps it dual feasible (its reduced cost changes sign exactly when the step passes it), and costs nothing in a pivot. The leaving row's infeasibility `delta` is a slope that each passed column lowers by `|a_rj| * (hi_j - lo_j)`. **[choice]**
1. The eligible columns are those of section 14, with ratios `|d_j| / |a_rj|`, taken in increasing order (ties: larger `|a_rj|` first, as now).
2. For each in turn, `slope = delta - |a_rj| * (hi_j - lo_j)`. While `slope > tol` (`tol = 1e-9 * (1 + delta)`) the column is flipped and `delta = slope`. The first column with `slope <= tol` enters the basis.
3. If the columns run out with `delta > tol`, the row cannot be made feasible: infeasible, as now when no column is eligible.
4. The primal values of the basic variables take every flip: `z_B(i) -= T[i][j] * (new bound - old bound)`; only then is the step of the entering column computed from what is left of the leaving variable's violation.

An infinite range (the logical variables of one-sided rows hold `1e300`) makes the slope negative at once, so such a column enters as before. The picks are made by repeated selection of the minimum, not a sort: the usual number of flips is small, and the cost is measured below, not assumed.

**Claim to measure.** The iterations fall most where many columns are boxed and cheap to flip (multi-knapsack relaxations, 0..1 variables); network LPs, which already match HiGHS, change little. **Gates:** the oracle (`check_highs.py`, the same 168 instances) must still agree to its tolerances; mutants of the flip (no flip made, flip to the wrong bound, the slope not lowered) must each be killed.

**17.1 results (measured: `scripts/bench_highs.py --runs 3`, compiler `5a5dd1f2`, one machine).** Gates: oracle 168 of 168, language, expand and CLI pass (the iteration-limit test of `lp_basic` now expects 2 iterations, not 3); the seven mutants of the long step and the one whose text changed are all killed. Iterations and time against HiGHS's dual simplex (ours minus start-up / HiGHS), before then after:

| instance | our iterations | ours/HiGHS dual |
|---|---|---|
| multi-knapsack 4000 items, 200 rows | 94,644 then 7,084 (HiGHS 471) | 142.6 then 11.1 |
| multi-knapsack 2000 items, 100 rows | 21,917 then 1,930 (258) | 40.3 then 4.0 |
| multi-knapsack 1000 items, 50 rows | 4,902 then 458 (126) | 11.3 then 1.2 |
| random dense 800x1600 | 43,028 then 25,655 (2,851) | 13.1 then 8.1 |
| random dense 400x800 | 9,020 then 7,102 (1,118) | 8.5 then 7.0 |
| transportation 100x160, assignment 100x100 | 369 then 364, 393 then 333 | 1.2 then 1.2, 1.3 then 1.0 |

The claim of 17.1 held: the boxed families gain most (a factor of 10 to 13 in iterations), the network LPs match HiGHS before and after. The random dense LPs, whose columns are boxed over a wide range, gain a factor of 1.3 to 1.7, so they remain 7 to 8 times behind and are what 17.2 is for. The cost of the repeated selection was not separated; it is inside the totals above.

**17.2 Dual steepest-edge pricing (written before the code).** The leaving row is now the one with the largest violation, which depends on how the rows are scaled. Dual steepest edge chooses the row maximising `viol_i^2 / w_i`, where `w_i = ||row i of B^-1||^2` is the squared length of the dual edge. **[choice]**
- In this tableau `B^-1` is the block of the `m` logical columns of `T` (the logical columns start as the identity and the pivot is Gauss-Jordan on all columns), so `w_i` is the sum of the squares of row `i` over the columns `n .. n+m-1`. At the slack basis it is 1 for every row (exact, no setup).
- **Exact, not updated by formula:** the textbook update of `w` needs `B^-1 rho_r` for every row (another `m^2` work and a place for drift). Here the pivot loop already rewrites each changed row, so it recomputes `w_i` from the new row in the same pass (the loop over `j` is split at `n`: structural columns as now; logical columns also accumulate `v*v`). A row with `f == 0` is not rewritten and keeps its `w_i`; the pivot row is scaled first and its `w_r` taken from the scaled row. The work added to an iteration is one multiply-add on `m` of the `n + m` cells of each changed row.
- Pricing: `score = viol^2 / w_i`; `delta` of the long step (17.1) is still the plain violation of the chosen row.

**Claim to measure.** Iterations fall again on the random dense LPs (where the long step helps little, the columns being boxed wide); the cost per iteration rises by at most about `m / (n + m)`. The net time is measured, not assumed: if the iterations fall less than the cost rises, the change is not kept, and the section says so. **Gates:** oracle, CLI and language gates as before; mutants of the pricing (violation not squared, weights not divided, weights not recomputed) must be killed.

**17.2 results (measured: `scripts/bench_highs.py --runs 3`, compiler `5a5dd1f2`, one machine, seed 7, minimum of 3 runs).** Gates: oracle 168 of 168, language, expand and CLI pass, and a new gate 5 (`scripts/check_iterations.py`) judges the iteration counts, because the oracle cannot see a worse pricing rule. The five mutants of the pricing: four were killed by the bounds of gate 5; one survived (the pivot row's weight set to 1 instead of taken from its row), because the counts moved only by two to four iterations, on transportation and assignment instances only (a scan of 160 instances: 12 differed, none on the dense or knapsack ones). Two exact counts were added to gate 5 and kill it. Time and iterations, before (17.1) then after (17.2); "ours" is the process minus start-up, "HiGHS" is `highs-ds` in-process:

| instance | our iterations (HiGHS) | ours (s) | HiGHS (s) | ours/HiGHS |
|---|---|---|---|---|
| random dense 800x1600 | 25,655 then 2,692 (2,851) | 26.50 then 3.06 | 3.26 then 3.24 | 8.1 then 0.9 |
| random dense 400x800 | 7,102 then 1,038 (1,118) | 1.80 then 0.30 | 0.26 then 0.27 | 7.0 then 1.1 |
| multi-knapsack 4000 items, 200 rows | 7,084 then 527 (471) | 3.35 then 0.262 | 0.30 then 0.306 | 11.1 then 0.9 |
| multi-knapsack 2000 items, 100 rows | 1,930 then 260 (258) | 0.257 then 0.039 | 0.065 then 0.065 | 4.0 then 0.6 |
| assignment 100x100 | 333 then 214 (257) | 0.027 then 0.013 | 0.028 then 0.026 | 1.0 then 0.5 |
| transportation 100x160 | 364 then 406 (260) | 0.043 then 0.049 | 0.035 then 0.036 | 1.2 then 1.4 |

Every one of the 21 instances still agrees with HiGHS's optimal value. The iteration counts are now within about ten percent of HiGHS's on the dense and knapsack families (the gap of section 15 was a factor of 8 to 200), and the cost per iteration of the weights was small enough that the time followed the iterations. **What this does not show:** it is HiGHS through scipy, on four generated families of at most 800 rows, with the model already expanded; the dense tableau still does `m * (n + m)` work per iteration and holds that many cells (32 million at most), so a model of tens of thousands of rows is out of reach however few iterations it takes; HiGHS wins there by exploiting sparsity (presolve, LU), which is the next step and is not claimed here. Transportation got slightly worse (more iterations than before 17.2, 1.4 times HiGHS), an unexplained regression of one family that is left open.

**Mutants after 17.2:** the whole suite of 45 gives 44 killed and 1 survived: the known one, "verified is always true", which can only be seen when the solver is already wrong (section 15). The five of the pricing were run with gate 5 added to the runner.
