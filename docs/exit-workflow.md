# Worked example: evolve an exit policy

This example is a small Boolean transition relation. It is independently written and does not reconstruct the user's private deflationary agent or measure trading returns.

## Fixed intent

Inputs are `holding`, `profit`, and `exit`. Outputs are `sell` and `hold_next`.

- Sell exactly when holding and at least one of the two signals is true.
- Keep holding exactly when already holding and not selling.
- Produce exactly one output pair for each admitted input.
- Preserve the explicit positive example: exit without profit must permit selling.

These requirements, variable domains, and the positive example remain unchanged throughout the session. There are 8 input cases and 32 complete input/output assignments.

## Starting error

```text
sell <-> (holding && (profit && exit))
```

The conjunction requires both signals. An exit signal without profit incorrectly keeps the position open. The initial checker emits three violation records: two forbidden behaviors and one positive-example mismatch. Those are three records describing two distinct input cases, not three independent bugs.

## Observed search

| Stage | Evaluations | Violations in best candidate | What happened |
|---|---:|---:|---|
| Initial check | — | 3 | The starting spec requires both signals. |
| Round 1, random seed 0 | 64 | 1 | Search repairs the exit-only case but still misses profit-only. |
| Round 2, random seed 1 | 128 | 0 | Retained candidates guide a valid repair using `!profit -> exit`. |
| Round 3, random seed 2 | 10 | 0 | An assistant-authored proposal simplifies that expression to `profit || exit`. |

The first two rounds use typed mutations and crossover, with no external correct-candidate proposal. The search evaluates hypotheses against the requirements; it does not parse English to infer the intended policy. The third round records a transparent external proposal fixture. Replaying the demo does not invoke an LLM or establish a model-performance result.

`!profit -> exit` is equivalent to `profit || exit`. The final selected formula is:

```text
(sell <-> (holding && (profit || exit)))
&& (hold_next <-> (holding && !sell))
```

The observed 202 evaluations include rechecks of retained candidates. Full session replay and independent verification are additional work. This is one fixed-seed illustration, not evidence of superiority over enumeration, a larger one-shot search, or a learned proposer.

## Concrete behavior change

| Holding | Profit | Exit | Starting output `(sell, hold_next)` | Repaired output |
|---|---|---|---|---|
| True | False | True | `(False, True)` | `(True, False)` |
| True | True | False | `(False, True)` | `(True, False)` |

The other six input cases retain their outputs. The complete relation gains two allowed assignments and removes the two incorrect ones. The final candidate is total and deterministic over all eight admitted input cases. An independently written expected-output calculation agrees on all 32 assignments.

## Reproduce and inspect

```bash
python scripts/run_exit_demo.py --out runs/exit-demo
python -m zeno_speccheck session-replay examples/deflationary_exit.json runs/exit-demo/session.json
python -m zeno_speccheck review examples/deflationary_exit.json runs/exit-demo/session.json --out runs/exit-demo/review.html
```

Open the HTML file locally. It shows all eight decision rows and expandable evidence for each round. `summary.json` records the actual selected formulas, AST sizes, candidate/parent identities, witness count and full-domain result. `session.json` contains all rounds and can be replayed; the two feedback files demonstrate what an agent receives after each search round. The report retains `approval: not_granted`.

The checked-in evidence also includes a native Tau cross-check. Reproduce it by adding `--tau-python`, `--tau-module-dir`, and `--tau-source-revision` to the demo script as described in [tau-runtime.md](tau-runtime.md). The exporter restricts sbf streams to Boolean values and translates a stateless relation. The native result checks causal realizability and universal requirement implication. It does not prove an unbounded financial state-machine invariant, and examples/determinism still use the finite checker.
