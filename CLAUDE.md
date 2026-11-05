# CLAUDE.md -- cancho-solve

Design before code: each verb and each part of the model language gets a section in `docs/design.md` before its implementation, and every claim in it is
either measured (with the command that measures it) or marked as a **choice** or **open**.

- **Agent-first, like cancho-opt, cancho-ml and cancho-stats.** JSON on standard output; an error is data with a stable `solve.<name>` rule tag, exit status 2
  and a repair. No model is ever logged.
- **The model is checked before anything is solved.** `solve check` refuses a model with a rule tag and a source position, the way cancho-gpu's compiler
  refuses a kernel. A solver never sees a model `check` would refuse.
- **An independent oracle.** Optimal values are held against HiGHS (LP, MIP) and, later, OR-Tools CP-SAT (CP); every solution is re-checked by `solve verify`,
  which shares no code with the search. Mutants: all killed, or each survivor explained.
- **Determinism.** The same model, options and seed give the same bytes. A feature that cannot keep that is refused or documented as the exception, with a test.
- **No source file over 2,000 lines. Every refusal has a rule tag. No input reaches a panic.**
- **Gates are written before the code they judge and must be able to fail.**
- **Measured claims only.** A claim found false is corrected in place, in the document that made it. Never state a speed against another solver that was not
  measured here.
- Licence EUPL-1.2, copyright Alpibru S.L. Commit trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`; PRs stay draft until the maintainer says
  merge; no force-push to main.
