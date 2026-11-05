# cancho-solve — design (S0 to S3 built) — DRAFT

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
| S3 | MIP: branch and bound over the LP | gate 4 passes for MIP (**built, section 19**; `verify` is not) |
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

## 18. Against OR-Tools (measured), and the sparse revised dual simplex (designed, not built)

### 18.1 Time against OR-Tools' LP solvers

`scripts/bench_ortools.py`, OR-Tools 9.15.6755 (`pywraplp`, GLOP and CLP, every option at its default, presolve included), installed in a scratch virtualenv (`pip install ortools scipy numpy`); the same generated instances as section 15 (seed 7); `solve run --relax` of the build at `f04bd05` (long step and steepest edge). Ours is the process minus start-up; OR-Tools is `Solve()` alone, after the model is built; HiGHS (`highs-ds` through scipy) is repeated for reference; minimum of 3 runs; one machine (Apple Silicon, `arm64`), one thread each.

| instance | rows x cols | ours (s) | GLOP (s) | CLP (s) | HiGHS (s) | ours/GLOP | ours/CLP |
|---|---|---|---|---|---|---|---|
| random dense 200x400 | 200 x 400 | 0.0222 | 0.0617 | 0.0171 | 0.0214 | 0.4 | 1.3 |
| random dense 800x1600 | 800 x 1600 | 2.70 | 4.64 | 4.73 | 2.81 | 0.6 | 0.6 |
| transportation 80x160 | 240 x 12,800 | 0.0306 | 0.0224 | 0.0197 | 0.0255 | 1.4 | 1.6 |
| transportation 100x160 | 260 x 16,000 | 0.0439 | 0.0275 | 0.0215 | 0.0311 | 1.6 | 2.0 |
| assignment 80x80 | 160 x 6,400 | 0.0071 | 0.0061 | 0.0022 | 0.0139 | 1.2 | 3.3 |
| assignment 100x100 | 200 x 10,000 | 0.0129 | 0.0116 | 0.0040 | 0.0227 | 1.1 | 3.2 |
| multi-knapsack 1000 items | 50 x 1,000 | 0.0051 | 0.0089 | 0.0061 | 0.0128 | 0.6 | 0.8 |
| multi-knapsack 4000 items | 200 x 4,000 | 0.2365 | 0.2881 | 0.3739 | 0.2590 | 0.8 | 0.6 |

(The full table of 14 instances is what `bench_ortools.py` prints; the rows above are a selection, the others lie between them.) All 14 agree with both OR-Tools solvers on the optimal value to 1e-6 relative. Reading: on the dense and the knapsack instances ours is at 0.4 to 0.8 times GLOP and 0.6 to 1.3 times CLP; on the network LPs (transportation, assignment) **ours is 1.1 to 1.6 times GLOP and 1.6 to 3.3 times CLP, slower**, and CLP is the faster of the two OR-Tools solvers there. **Not claimed:** nothing about instances larger than these (the dense tableau cannot hold them), nothing about MIP or CP (S3, S5), nothing about presolve-friendly structured models (ours has no presolve), and a Python call is inside OR-Tools' figure (its overhead is a fraction of a millisecond, which matters only for the smallest rows). The iteration count OR-Tools reports (`iterations()`) is not comparable with ours: it counts what GLOP does after its presolve.

### 18.2 Why the dense tableau stops here: the basis is sparse where the problems are

The tableau updates `m * (n + m)` cells each iteration whatever the model. What a sparse method would carry instead is the LU factorisation of the basis. `scripts/basis_density.py` takes the optimal basis from GLOP (its `basis_status`), factorises it with SuperLU (COLAMD ordering), and counts:

| instance | m | n | nnz(B) | nnz(L+U) | m x m | tableau cells m(n+m) | (L+U)/m^2 |
|---|---|---|---|---|---|---|---|
| random dense 200x400 | 200 | 400 | 10,312 | 16,121 | 40,000 | 120,000 | 0.40 |
| random dense 400x800 | 400 | 800 | 46,554 | 77,652 | 160,000 | 480,000 | 0.49 |
| multi-knapsack 2000 items | 100 | 2,000 | 4,654 | 6,322 | 10,000 | 210,000 | 0.63 |
| transportation 100x160 | 260 | 16,000 | 477 | 905 | 67,600 | 4,227,600 | 0.013 |
| assignment 100x100 | 200 | 10,000 | 399 | 678 | 40,000 | 2,040,000 | 0.017 |

On the network LPs the factor of the basis has under 1,000 nonzeros where the tableau rewrites four million cells an iteration: the factor is thousands of times smaller than the tableau (the work of an iteration also includes the pricing and the eta file, which were not measured). That gap in size is the likely, not a measured, source of the 1.6 to 3.3 times behind CLP. On the dense random LPs and the knapsack the factor is 40 to 63 percent full, so a sparse method has little to gain there (and its overheads, the eta file and the pricing through the rows, would cost more than they save): **the tableau is the right method for those, and the sparse one is for the structured models.** One basis per instance, at the optimum only; the bases along the way are denser or sparser and were not measured.

### 18.3 Design of the sparse revised dual simplex **[choices unless marked]**

It keeps everything of 14 and 17 (the same dual feasibility by boxing, the long step, the steepest-edge pricing) and replaces the tableau by a factorised basis.
- **Data.** The checker already holds the model by rows (`row_start`, `term_col`, `term_coef`, section 6). The solver builds the column form (a counting sort over the same terms) once; the logical columns are implicit unit vectors. Memory is `O(nnz(A) + nnz(L+U) + etas + m + n)`.
- **One iteration** (the names are the textbook's): choose the leaving row `r` by `viol^2 / w_r`; BTRAN `rho = e_r B^-1`; price the row `alpha_r = rho A_N` through the rows of `A` for the nonzeros of `rho` only (so the work follows the sparsity of `rho`); the bound-flipping ratio test of 17.1 over the candidates of `alpha_r`; FTRAN the entering column `alpha_q = B^-1 a_q` and one more FTRAN for the weight update `tau = B^-1 rho`; update the basic values, with the flipped columns' effect as one extra FTRAN of `sum a_j * delta_j`, the reduced costs by `alpha_r`, and the weights by the usual formula (not the exact recomputation of 17.2, which needs the tableau).
- **Factorisation.** LU with Markowitz pivot selection and a threshold test (`u = 0.1`), singletons first (network bases are nearly triangular), triangular solves skipping zeros; the basis change is a product-form eta (simplest; Forrest-Tomlin is **open**); **refactorise** every 64 iterations (**open**: choose by measuring), and at once when `alpha_q(r)` and the pivot taken from the row disagree by more than `1e-7` relative. At each refactorisation the basic values, the reduced costs and the weights' consistency are recomputed from scratch, which stops the drift of the updates.
- **Determinism.** Fixed order everywhere, no hashing, no threads; ties as in the dense solver.
- **Limits.** The 32-million-cell ceiling goes away; the limits of the model checker (16,384 variables, 16,384 rows, 1,048,576 nonzeros, section 6) become the binding ones. Raising them is a change of `layout.cho` through `gen_layout.py` and is **open**; the benchmark below stays within them.
- **Both solvers stay.** The dense tableau is kept (`solve run --method dense|sparse|auto`, **open**: the rule for `auto` follows from 18.2: the tableau while the model is dense or small, the sparse method when the model is sparse). The dense solver is also the second oracle of the sparse one: the same model must give the same optimal value from both, a check that shares no code with the factorisation.

**Stages, each measured before the next** (the dense solver's discipline of sections 14 to 17):
1. **Sparse linear algebra alone** (`lib/lp/sparse.cho`): column form, LU, FTRAN and BTRAN with etas. Gate: solves against scipy's `splu` on random sparse bases, residual under `1e-9`; mutants of the pivot threshold, the permutation and the eta application.
2. **The revised dual simplex on top.** Gates: the oracle (`check_highs.py`, same 168 instances) and the dense solver as second oracle; the iteration-count gate with bounds from the dense solver's counts; mutants.
3. **The benchmark** on the families of 18.1 and on the larger network LPs the tableau cannot hold, within the limits above.

**Claim to measure, and what would refute it.** On the network LPs the time per iteration falls by a factor of the order of `m(n+m) / (nnz(L+U) + pricing)`, hundreds to thousands, and the total time reaches CLP's; a result more than 2 times behind CLP on transportation or assignment instances of the sizes of 18.1 means the design is not enough and this section is corrected. On the dense LPs the sparse solver is expected to be *slower* than the tableau; if it is not, `auto` is simpler than planned.

## 19. S3: mixed-integer solving by branch and bound (written before the code)

Everything in this section is a **choice** or a claim **to measure**, until a results subsection says otherwise. S3 replaces the refusal `solve.not-built` for a model with `bool`/`int` variables by a search; `--relax` stays and still solves the relaxation.

### 19.1 The search **[choices]**

**Where the model comes from.** A node is the root model with tighter bounds on some integer columns; the LP of a node is solved by the dense dual simplex of section 14 (long step 17.1, steepest edge 17.2) behind a thin interface (`lib/mip/lpeng.cho`: `init`, `set_bounds`, `refresh`, `solve`, `copy`, `value`) so that the sparse solver of section 18 can replace it without touching the search. `lib/lp/simplex.cho` is split into `init_state` (everything before the loop) and `dual_loop` (the loop), `solve` keeps its signature and behaviour (gate 4 and the iteration counts of gate 5 are unchanged by it: a check).

**Warm start.** Every variable is boxed, so changing a bound never breaks dual feasibility: a nonbasic column keeps the side it sits on (its reduced cost keeps its sign) and moves to the new bound on that side; a basic column keeps its value and becomes primal infeasible, which is what the dual simplex repairs. After the change `refresh` recomputes the basic values from the nonbasic ones (`z_B = -T z_N`), and `dual_loop` runs from the existing tableau.

**What is kept per node.** A node is five numbers and a link: `(parent, column, lo, hi, bound, depth)`; its bounds are the root's intersected with the changes on the path to the root. No tableau is stored per open node (that would be `m (n + m)` floats each). Two tableaux exist: the *working* one and a copy of the *root's optimal* one. **A node is entered in one of two ways:** by *plunging* (the child of the node just solved, in place: the working tableau is the parent's, one bound changes) or by *restoring* (copy the root tableau, apply the path's changes, `refresh`, `dual_loop`). The root tableau is dual feasible and every bound on a path only tightens, so restoring needs no phase 1; it costs one copy and the dual pivots needed to absorb the whole path rather than one change. Whether storing the parent's tableau would pay is **open** and is measured only through the iteration counts per node (19.5).

**Node selection.** After a node that is pruned, integral or infeasible, the next node is taken from the open list by (a) `depth`: the most recently created, or (b) `best`: the smallest parent bound, ties to the older node; and a node with children always plunges into one child first. So (a) is plain depth-first and (b) is the usual hybrid (plunge, then best bound). The default is **best** (measured, 19.5.2: it solves more instances in fewer nodes than depth-first); the other stays as `--node-select depth|best`. Pure best-first without plunging is not built.

**Plunge direction.** The child whose side is nearest the LP value (up when the fractional part is at least one half; ties up). The other is pushed. (An ablation flag measures the opposite order.)

**Branching.** Variable: the integer column whose LP value is farthest from an integer (fractional part closest to one half; ties to the lower column index) — `fractional`. Then **pseudo-cost** (`--branching pseudo`) if it earns its place: for each column the average objective increase per unit of change in each direction, from the children already solved; a column without history in a direction uses the average over columns that have one (1 when none has); score = product of the two predicted increases (each floored at 1e-6); **the default is `pseudo`** (measured, 19.5.2); `--branching fractional|pseudo`. As built, the average used for a column without history is the mean over all columns of the sums seen so far in that direction (1 when none), and a child whose LP is infeasible contributes nothing.

**Pruning.** A node is cut when its LP is infeasible, or when its LP value `z` (always in minimisation form, `z = sign * (c x + c0)`) satisfies `z >= incumbent - 1e-9 (1 + |incumbent|)`. If the objective can only take whole values (every term has a whole coefficient on an `int`/`bool` column and the constant is whole) the cut is `z > incumbent - 1 + 1e-6`, which cuts more. The dual simplex's own objective rises monotonically, so a cut-off *inside* the loop is possible; it is **not built** (an open improvement). A node's LP is integral when each integer column is within `1e-6` of a whole number. **As built:** the rounded point must also satisfy every row within `1e-7 (1 + |rhs|)` before it is offered as an incumbent (rounding a value that is off by 1e-6 can move a row by more than the `1e-6` that `verified` allows); if it does not, the search branches on the column with the largest remaining fractional part above `1e-9` instead, and a node whose columns are all within `1e-9` of whole numbers but whose rounded point still fails is dropped (the LP then claims feasibility to 1e-9 and the rounded point disagrees to 1e-7: a numerical corner that no generated instance reached, **unverified**).

**Incumbent.** On an integral LP the integer columns are rounded to whole numbers, the objective is **recomputed from the rounded point and the model** (not taken from the tableau), and it replaces the incumbent only if it is better by more than `1e-9 (1 + |inc|)` (so equal-valued points never replace it: determinism does not depend on tie noise). A cheap **rounding heuristic** runs at every node of depth up to 8 whose LP is fractional (as built; a **choice**, measured by an ablation, 19.5.2): round every integer column to the nearest whole number, keep the continuous ones as the LP has them, and accept the point only if the rows hold within `1e-9 (1 + |rhs|)`. For a model that is all integer that is a full feasibility test; for a mixed model the continuous columns are *not* re-solved, so the heuristic rarely succeeds there and its value is measured, not assumed.

**Limits (no wall clock, so the same input and options give the same bytes).**
`--node-limit N` (nodes whose LP is solved, the root included; default 200,000, at most 2,000,000 or `solve.too-large`; 0 solves nothing and answers `unknown`), `--iteration-limit N` (now the *total* dual simplex iterations of the search; one LP is also capped at the default of section 14, `100 (rows + columns) + 1000`, and hitting that cap ends the search as `lp-limit`). Each limit ends the search with the open list unproven.

**Result (section 5), exit status.** `status`: `optimal` (the search finished with an incumbent: proof, exit 0), `infeasible` (finished without one: proof, exit 0), `feasible` (a limit and an incumbent: exit 1; `bound` and `gap` say how far), `unknown` (a limit and no incumbent: exit 1; `bound` is the best proven bound). `limit` is one of `nodes`, `iterations`, `lp-limit`. `bound` is the best proven bound in the model's own sense (the least parent bound over the open nodes, the plunge node included), equal to `objective` when `optimal`; `gap = |objective - bound| / max(1, |objective|)`. `stats` gains `nodes` and `branched`. A hidden `--experiment N` (bit 1: no whole-objective cut, bit 2: no rounding heuristic, bit 4: plunge to the far child) exists only for the ablations of 19.5.2 and the gate that holds their counts. `verified`/`max_violation` now include integrality: the largest `|x - round(x)|` over integer columns is part of the maximum, and `x` prints the rounded values. An unbounded outcome stays impossible (every column is boxed).

**Refusals.** The only new ones are `solve.usage` (a bad value of a new flag) and `solve.too-large` (a node limit above 2,000,000, or the tableau ceiling of section 14). No input reaches a panic: the node arena has a fixed capacity of `2 * node_limit + 2` and the loop stops before it is exceeded.

**`solve verify` (not built; the next milestone).** The verb must check a *given* solution against the model with no search code, and the binary has no filesystem, so both would have to arrive on standard input; that needs a solution format and a JSON reader in `solve` (S2 has neither), a milestone of its own. What S3 provides instead is the Python checker of the gates (`scripts/hs.py`, `violation`, `objective_of`), which shares no code with the search and re-evaluates every bound, row and integrality from `solve expand` output alone, and the `verified` field of the result (which is computed by code that reads the checked model, not the tableau, but is not independent of the binary).

### 19.2 Gates (written before the code) **[to run]**

1. **Hand-derived models** in `tests/mip/*.sol` with a `//~ EXPECT status objective` line derived by hand in a comment beside each: an integer-infeasible model with a feasible relaxation (`2x + 2y == 3`, x, y integer), a model whose relaxation is already integral (a totally unimodular assignment: nodes = 1), an equality knapsack (a subset sum that has a solution and one that has none, one by parity), a knapsack whose relaxation is fractional and whose optimum is known by enumeration, a general-integer example with negative bounds, a mixed model (integer and real), and a node-limit case (`feasible` with a gap, and `unknown`). A bound-gap case: a model with an incumbent found and the search cut by the node limit must print `bound <= objective` (minimisation) and a `gap`. **As built** the `feasible`-with-gap case is not hand-derived (a node count at which an incumbent first appears cannot be derived by hand) but checked as a property on 462 limited runs of generated models (gate 6, part 3); the hand-derived limit cases are `knapsack_node_limit.sol` (one node: `unknown`, bound 21.14), `knapsack_iteration_limit.sol` (no iteration: `unknown`, no node solved) and `huge_gap.sol` (50 nodes of a model whose branching walks a range of a million: `unknown` with a bound, and exactly 50 nodes).
2. **Oracle** `scripts/check_mip.py`: fixed-seed generated instances from `scripts/lpgen.py` — 0/1 knapsack, multi-dimensional knapsack, assignment, set cover, general-integer (bounds -3..9, mixed signs, rows of the three senses), mixed integer-continuous, and infeasible ones — are expanded with `solve expand`, solved by `scipy.optimize.milp` (HiGHS), and required to agree on status and optimal value (1e-6 relative); the printed `x` is re-evaluated in Python for bounds, rows and integrality; `bound`/`gap` are checked on limited runs (`bound <= opt <= objective` for minimisation); two runs give identical bytes. OR-Tools CP-SAT (integer models with integer coefficients only) and SCIP (`pywraplp`) are the second oracle on a subset where they apply (`scripts/check_mip.py --ortools`).
3. **Gate 3 (no panic)** extends to `run` without `--relax`, with and without limits, on cuts and mutations of the corpus; the check that an integer model without `--relax` is refused `solve.not-built` is **deliberately replaced** by one that it is solved.
4. **Gate 5 (iterations)** keeps its bounds for the LP; it must not move (the refactor into `init_state`/`dual_loop` changes no count).
5. **Gate 7 (`scripts/check_nodes.py`, added while measuring):** the oracle cannot see a worse branching rule or a weaker cut, so the node and iteration counts of six fixed instances under seven option sets are held exactly. It is a **ratchet, not an independent check**: the numbers were recorded from the code itself; it detects a change of behaviour, not a wrong one. Also: `hs.py` asks HiGHS for `mip_rel_gap = 0` (its default stops at a relative gap of 1e-4, which would make the oracle weaker than the claim).
6. **Mutants** (appended to `scripts/mutants.py`; every one killed or each survivor explained): branching on the wrong side or on a column that is integral, the plunge going to the wrong child, the cut `>=` against `>`, the objective-integrality cut off by one, the incumbent replaced by a worse point, the incumbent objective taken from the LP not the rounded point, the bound of a child not tightened, `refresh` skipped after a bound change, the path not applied when restoring, `bound` not the minimum over the open list, the integrality tolerance loosened, the node limit off by one.

### 19.3 Benchmark (written before the code) **[to run]**

`scripts/bench_mip.py`: the generated families at growing sizes (0/1 knapsack, multi-dimensional knapsack, assignment, set cover, a general-integer family) against HiGHS (`scipy.optimize.milp`, whole call), OR-Tools SCIP (`pywraplp`, `Solve()`) and CP-SAT (integer coefficients only), minimum of several runs; for each, wall time, our nodes and iterations against theirs where reported (HiGHS reports `mip_node_count`; CP-SAT `num_branches`; SCIP `nodes()`), the status and the objective. Time limits are given to the others (not to ours); instances where someone stops at a limit are marked. The results, whatever they are, go in 19.5.

### 19.4 What was built

`lib/lp/simplex.cho` is split into `init_state` and `dual_loop` (`solve` is unchanged; gates 4 and 5 give the same counts as before: 168 of 168, and the iteration bounds). `lib/mip/lpeng.cho` (about 110 lines) is the thin LP interface; `lib/mip/mip.cho` (631 lines) is the search; `tools/solve/emit.cho` gained `mip_report` and `main.cho` the flags `--node-limit`, `--node-select`, `--branching` (and the hidden `--experiment`). `solve run` on a model with integer variables is solved; the refusal `solve.not-built` stays only for the reserved CP keywords. Gate 3 (`check_cli.py`) used to expect the refusal for an integer model without `--relax`: **that expectation was replaced deliberately** by "it is solved, objective 13" (the knapsack of `tests/ok/knapsack.sol`: items 1, 2 and 3 weigh 7 and are worth 13; adding item 0 (weight 12) exceeds 15), plus six bad-flag cases. `cancho fmt --check` passes, and the compiler is `5a5dd1f2`.

### 19.5 Results (measured)

All numbers: one machine (Apple Silicon `arm64`, macOS 26.2), the cancho-written compiler at `5a5dd1f2` (LLVM code generator), OR-Tools 9.15.6755, scipy 1.18.1 (its bundled HiGHS), Python 3.14; one seed (7) per instance; the machine was not otherwise idle during the ablations (counts are exact, times are not), and was during the benchmark tables.

**19.5.1 Gates.** Gate 6 (`scripts/check_mip.py --ortools`): 10 hand-derived models; 194 generated instances (30 knapsacks, 12 multi-knapsacks, 10 assignments, 20 set covers, 16 subset sums, 60 general-integer, 40 mixed, 6 bin packings): 179 optimal and 15 infeasible, **every one agrees with HiGHS** (status, and objective to 1e-6 relative; HiGHS asked for a zero gap), 110 of them also with an exhaustive enumeration written in the gate (a third opinion that shares no code with either solver; HiGHS and the enumeration agree on all 110), and 142 integer-only ones also with CP-SAT and SCIP; the printed `x` is re-evaluated in Python for bounds, rows and integrality; 462 runs under node limits 1, 3 and 8 (`bound` brackets the optimum, the incumbent is feasible, `gap` is present); 28 pairs of runs give identical bytes; 658 runs under the other option sets reach the same optimum. The gate was shown able to fail: before the code existed its quick mode failed on all 48 cases it ran (`solve.not-built`). Gate 7 (exact counts): 42 instance/option pairs. Gates 1 to 5 pass (language, expand, 168-case LP oracle, 9,393 CLI runs, iteration bounds). The oracle's *own* answer was checked: HiGHS and the enumeration disagree nowhere.

**Mutants.** 27 new mutants of the search, the LP interface and the report: **25 killed, 2 survive, 0 invalid.** Survivors: (a) "verified is always true (MIP)" — the same explained survivor as section 15: `verified` is false only when the search returns a point that violates the model, and the oracle would have failed first; (b) "a node as good as the incumbent is not cut" (`z >= inc - tol` changed to `z > inc - tol`): the two differ only when `z` equals `inc - 1e-9 (1 + |inc|)` *exactly* in floating point, which no instance produces; for a whole-valued objective the other cut applies first. It is an equivalent mutant for practical purposes, **not proved equivalent**. The first run of the suite exposed no gap in the corpus, but only because the node and iteration gate (7) was written *because* I expected effort-only mutants (pruning with `>=`, selection order, plunge side) to survive the oracle; they are killed by gate 7 and by nothing else. The 45 mutants of sections 13 to 17 were not run again after the `init_state`/`dual_loop` split (their texts were checked to still be present and gates 4 and 5 give identical counts); **unverified** that each is still killed.

**19.5.2 The decisions, measured.** `bench_mip.py --ablate`, 31 instances (the families of the benchmark below at growing sizes), node limit 200,000. Instances that stop at the limit count 200,000. The first four rows were measured with the options spelled out; "depth + fractional" was the draft default.

| option set | solved of 31 | total nodes | geometric mean of nodes |
|---|---|---|---|
| depth + most-fractional | 28 | 912,020 | 432 |
| best-bound + most-fractional | 29 | 526,129 | 258 |
| depth + pseudo-cost | 30 | 635,113 | 253 |
| **best-bound + pseudo-cost (the default)** | **31** | **297,645** | **209** |
| depth + fractional, whole-objective cut off | 23 | 1,972,801 | 1,322 |
| depth + fractional, rounding heuristic off | 28 | 913,514 | 471 |
| depth + fractional, plunge to the far child | 28 | 884,085 | 244 |

Reading: (1) best-bound selection and pseudo-cost branching each cut the nodes and together cut them to a third of the draft default, and only that pair solved all 31; it is the default. (2) The whole-objective cut (`z > inc - 1 + 1e-6`) is worth a factor of two in total nodes and five more instances solved (28 against 23): it is large for the same reason it is cheap (every knapsack, set cover and assignment here has a whole objective). (3) The rounding heuristic changes the total by 0.2 percent and the geometric mean by 8 percent: **it earns little**; it is kept because switching it off lowers the node count on none of the 31 instances and raises it on 5 (by 14 to 848 nodes, all multi-knapsacks; mkp 50x10: 269 to 1,117), not because it is shown to matter much. (4) Plunging to the far child lowers the geometric mean but is dominated by single instances: it needs 10 nodes instead of 11,801 on the 1,000-item knapsack and 7,778 instead of 269 on the 50x10 multi-knapsack. It is not a safe default; the data do not support choosing a direction by family. These ablations were run with depth + fractional as the base (the first default), not best + pseudo; the effect of each on the final default was not separately measured (gate 7 holds the counts of every option on six instances). Best-bound is *worse* on single instances (knapsack of 200 items: 6,006 nodes against 1,600; 8 items and 4 bins: 156 against 80), so "wins" means on the total and the count solved, not on every row.

**19.5.3 What a node costs.** Half of the nodes are reached by plunging and half by restoring (mkp 100x20: 17,895 nodes, 9,316 branched, 8,578 restored; general-integer 50x50: 151,141, 78,719, 72,421). The cost is 1 to 18 dual simplex iterations for a node (10.0 and 18.2 on the two models above), 12 to 75 microseconds for a node (whole process time over nodes: 27 for the 100x20 multi-knapsack, 75 for the 50x50 general-integer model, 12 for the 1,000-item knapsack, where one iteration solves a node). Whether keeping the parent's tableau for the siblings would cut the iterations is **open** (not tried); the restore costs a copy of the root tableau plus the pivots that absorb the whole path.

**19.5.4 Against HiGHS, SCIP and CP-SAT.** `scripts/bench_mip.py --runs 3 --limit 60` and `--extra --runs 1 --limit 40`. Ours: wall clock of the whole `solve run` process (includes process start-up, reading and expansion; the smallest instances take 2 ms in all), minimum of 3 runs, default options (best-bound, pseudo-cost, node limit 200,000). HiGHS: `scipy.optimize.milp` with `mip_rel_gap = 0` (its default is 1e-4), the call alone. SCIP: `pywraplp` with `RELATIVE_MIP_GAP = 0` (default 1e-4), `Solve()` alone, one thread. CP-SAT: one worker, integer models only, `Solve()` alone. The others get a time limit (60 s, then 40 s), ours does not (it has the node limit). The objective of every instance that more than one solver proved agrees to 1e-6 relative. Rows that end "(feasible)" mean our search reached 200,000 nodes with an incumbent and no proof.

| family | size | rows x cols | ours (s) | our nodes | HiGHS (s) | nodes | SCIP (s) | nodes | CP-SAT (s) | branches |
|---|---|---|---|---|---|---|---|---|---|---|
| knapsack | 30 items | 1 x 30 | 0.002s | 54 | 0.008s | 1 | 0.000s | 0 | 0.001s | 0 |
| knapsack | 60 items | 1 x 60 | 0.002s | 2 | 0.004s | 1 | 0.000s | 0 | 0.000s | 0 |
| knapsack | 100 items | 1 x 100 | 0.004s | 1118 | 0.013s | 1 | 0.000s | 0 | 0.001s | 0 |
| knapsack | 200 items | 1 x 200 | 0.027s | 6006 | 0.033s | 1 | 0.001s | 0 | 0.002s | 0 |
| knapsack | 500 items | 1 x 500 | 0.018s | 3198 | 0.025s | 1 | 0.004s | 0 | 0.011s | 0 |
| knapsack | 1000 items | 1 x 1000 | 0.131s | 11801 | 0.051s | 1 | 0.014s | 0 | 0.040s | 0 |
| mkp | 30 x 5 | 5 x 30 | 0.004s | 293 | 0.057s | 23 | 0.040s | 32 | 0.011s | 892 |
| mkp | 50 x 5 | 5 x 50 | 0.005s | 104 | 0.045s | 2 | 0.024s | 2 | 0.004s | 246 |
| mkp | 50 x 10 | 10 x 50 | 0.005s | 263 | 0.117s | 18 | 0.042s | 16 | 0.013s | 879 |
| mkp | 100 x 10 | 10 x 100 | 0.037s | 3271 | 0.457s | 613 | 0.307s | 573 | 0.166s | 10269 |
| mkp | 100 x 20 | 20 x 100 | 0.451s | 17895 | 2.839s | 11318 | 2.854s | 8501 | 0.792s | 80437 |
| mkp | 200 x 10 | 10 x 200 | 0.263s | 13448 | 1.374s | 3668 | 1.486s | 3775 | 1.373s | 63595 |
| assignment | 20 x 20 | 40 x 400 | 0.005s | 1 | 0.004s | 1 | 0.003s | 1 | 0.011s | 5084 |
| assignment | 50 x 50 | 100 x 2500 | 0.007s | 1 | 0.019s | 1 | 0.019s | 1 | 0.961s | 81898 |
| assignment | 100 x 100 | 200 x 10000 | 0.020s | 1 | 0.100s | 1 | 0.084s | 1 | 26.599s | 1752159 |
| set cover | 30 rows, 50 sets | 30 x 50 | 0.005s | 1 | 0.003s | 1 | 0.001s | 1 | 0.001s | 439 |
| set cover | 60 rows, 100 sets | 60 x 100 | 0.005s | 1 | 0.003s | 1 | 0.001s | 1 | 0.127s | 39982 |
| set cover | 120 rows, 200 sets | 120 x 200 | 0.008s | 4 | 0.165s | 1 | 0.030s | 1 | 60.000s (limit) | 9516999 |
| set cover | 200 rows, 400 sets | 200 x 400 | 0.036s | 18 | 0.482s | 1 | 0.179s | 1 | 60.000s (limit) | 6476792 |
| set cover | 300 rows, 300 sets, dense | 300 x 300 | 1.571s | 265 | 2.269s | 19 | 0.986s | 12 | 60.000s (limit) | 19814451 |
| set cover | 400 rows, 600 sets | 400 x 600 | 0.100s | 12 | 0.487s | 1 | 0.352s | 1 | 60.000s (limit) | 3771028 |
| general int | 10 x 10 | 10 x 10 | 0.006s | 15 | 0.001s | 0 | 0.000s | 0 | 0.000s | 0 |
| general int | 20 x 20 | 20 x 20 | 0.018s | 2667 | 0.062s | 137 | 0.037s | 173 | 0.018s | 1551 |
| general int | 30 x 30 | 30 x 30 | 0.035s | 3110 | 0.199s | 781 | 0.192s | 591 | 0.082s | 4270 |
| general int | 40 x 40 | 40 x 40 | 2.848s | 78028 | 3.988s | 26454 | 5.825s | 44329 | 2.841s | 101001 |
| general int | 50 x 50 | 50 x 50 | 11.083s | 151141 | 9.066s | 40680 | 3.601s | 25365 | 10.287s | 423927 |
| mixed | 30 x 40 | 30 x 40 | 0.010s | 424 | 0.184s | 49 | 0.131s | 224 | - | - |
| bin packing | 8 items, 4 bins | 12 x 36 | 0.006s | 156 | 0.004s | 1 | 0.002s | 1 | 0.002s | 175 |
| bin packing | 12 items, 6 bins | 18 x 78 | 0.006s | 50 | 0.003s | 1 | 0.001s | 1 | 0.003s | 507 |
| bin packing | 15 items, 8 bins | 23 x 128 | 0.039s | 2043 | 0.003s | 1 | 0.002s | 1 | 0.003s | 303 |
| bin packing | 20 items, 10 bins | 30 x 210 | 0.073s | 2254 | 0.003s | 1 | 0.004s | 1 | 0.008s | 1114 |

Larger instances (one run, 40 s limit for the others; for "bin packing 30 items, 12 bins" all four solvers answer *infeasible*; the script's label "limit" for SCIP and CP-SAT is its generic text):

| family | size | rows x cols | ours (s) | our nodes | HiGHS (s) | nodes | SCIP (s) | nodes | CP-SAT (s) | branches |
|---|---|---|---|---|---|---|---|---|---|---|
| mkp | 100 x 30 | 30 x 100 | 0.577s | 14528 | 3.495s | 11073 | 3.428s | 4940 | 1.069s | 102364 |
| mkp | 250 x 25 | 25 x 250 | 10.965s (feasible) | 200000 | 40.006s (status 1) | 107806 | 40.000s (limit) | 160455 | 40.000s (limit) | 744907 |
| set cover | 1000 rows, 1500 sets | 1000 x 1500 | >40s (timeout) | - | 12.914s | 919 | 15.609s | 615 | 40.001s (limit) | 2176627 |
| set cover | 600 rows, 600 sets, dense | 600 x 600 | >40s (timeout) | - | 38.771s | 8492 | 40.000s (limit) | 3861 | 40.004s (limit) | 7218110 |
| general int | 60 x 60 | 60 x 60 | 9.130s (feasible) | 200000 | 24.794s | 101212 | 16.655s | 99608 | 40.000s (limit) | 1243091 |
| mixed | 60 x 80 | 60 x 80 | 0.448s | 6385 | 2.001s | 3879 | 1.104s | 2828 | - | - |
| bin packing | 30 items, 12 bins | 42 x 372 | 0.007s (infeasible) | 1 | 0.004s (infeasible) | - | 0.006s (infeasible) | 1 | 0.011s (infeasible) | 671 |
| knapsack | 5000 items | 1 x 5000 | 5.740s (feasible) | 200000 | 0.224s | 1 | 2.498s | 88 | 2.472s | 13415 |

What this shows, and nothing past it:
* **On these families up to roughly 100 to 200 integer variables and a few hundred rows we are as fast as, or faster than, HiGHS and SCIP in wall clock, with 1.6 to 19 times as many nodes on the multi-knapsack and general-integer families** (multi-knapsack 100x20: 0.45 s, 17,895 nodes; HiGHS 2.84 s, 11,318; SCIP 2.85 s, 8,501; CP-SAT 0.79 s). The reason is not a better search: it is that a node costs us 27 microseconds and the others spend more for a node (presolve, cuts, heuristics, a Python call).
* **On structure that cuts and presolve exploit we are far behind in nodes.** 0/1 knapsack: HiGHS and SCIP prove optimality in 0 or 1 nodes, we need 54 to 11,801 and 200,000 nodes without a proof at 5,000 items (5.7 s against 0.22 s HiGHS and 2.5 s SCIP). Bin packing with 15 and 20 items: 1 node for HiGHS and SCIP, 2,043 and 2,254 for us. We have no cuts (cover, Gomory, flow), no presolve (no coefficient tightening, no probing), no restarts and a single diving rule; these account for the gap in nodes **by inference, not measured** (no run with their cuts turned off was made).
* **The dense tableau, not the search, limits us on large LPs.** Set cover with 1,000 rows and 1,500 sets did not finish in 40 s (HiGHS 12.9 s, SCIP 15.6 s) and the 600x600 dense one did not either (HiGHS 38.8 s): the root LP alone is a dense `m (n + m)` tableau. The sparse revised simplex of section 18 is the change this needs, and the LP engine is a thin interface for that.
* **Hard random general-integer models are about even at 40x40 to 50x50** (2.8 s against 4.0 s HiGHS, 5.8 s SCIP, 2.8 s CP-SAT at 40x40; at 50x50 11.1 s against 9.1 s, 3.6 s and 10.3 s) and at 60x60 we stopped at 200,000 nodes without a proof where HiGHS (24.8 s, 101,212 nodes) and SCIP (16.7 s, 99,608) finished: our nodes there are about twice HiGHS's, and the node limit is what ended us.
* **Node counts are not comparable one for one.** HiGHS counts after presolve and cuts, CP-SAT's `branches` are search decisions of a different kind, and ours include every node whose LP was solved including infeasible ones. They say where the gap is, not by how much.

**Not claimed.** One seed per size, random and textbook families (no MIPLIB), one machine, one thread for the others (HiGHS's thread count through scipy was not controlled). Nothing about models with more than about 2,000 columns or rows (the dense tableau), nothing about numerically hard coefficients (every coefficient here is a small integer), nothing about equality-heavy or big-M models beyond the one bin-packing family, and no claim that the search is complete in the presence of numerical trouble (the drop-the-node corner of 19.1 was never reached). `solve verify` is not built.

**Open, in the order I would take them:** the sparse LP for the large instances (section 18); cover and Gomory cuts at the root and a presolve (these are what the 0 and 1 node results of HiGHS and SCIP on knapsack and bin packing come from); the dual objective cut-off *inside* the simplex loop; storing the parent's tableau for the sibling; reliability branching in place of pure pseudo-cost; `solve verify`.
