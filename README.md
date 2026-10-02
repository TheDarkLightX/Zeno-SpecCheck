# Zeno-SpecCheck

**Evolve specifications against fixed requirements, with evidence for each candidate.**

Zeno-SpecCheck is an initial working CLI/library for specification review and evolutionary repair. It combines typed mutation, crossover, agent proposals, counterexamples, and formal decision procedures. It supports a small exhaustive Boolean reference model and an optional native Tau backend.

The human owns intended behavior. An agent may propose formulas; it cannot change the frozen requirements through the proposal interface or grant its candidate approval. A passing report means the configured obligations passed within the reported scope. It does not establish that the requirements express everything the human intended.

## Quick start

Python 3.11+; the reference checker has no runtime dependencies. From this checkout:

```bash
python -m zeno_speccheck check examples/authorization.json
# Expected: exit 1 and a witness showing that the seed permits denying authorization.

python -m zeno_speccheck evolve examples/authorization.json --seed 0 --max-evaluations 64 --out runs/auth.json
python -m zeno_speccheck replay examples/authorization.json runs/auth.json

python -m zeno_speccheck evolve examples/deflationary_exit.json --seed 0 --max-evaluations 512 --out runs/exit.json
python -m unittest discover -s tests -v
```

Optional installation: `python -m pip install -e .` provides the `zeno-spec` command.

The exit example is an independently written illustration: a held position can be sold on a profit signal **or** an exit signal. It is not a reconstruction of a private deflationary agent, a financial model, or a claim of profitable trading. `hold_next` is an output of a one-step relation; the example does not prove an unbounded state-machine invariant.

## What works

| Capability | Boolean reference model | Native Tau |
|---|---|---|
| Fixed English + formula requirements | Yes | Yes |
| Positive/negative examples | Complete Boolean assignments | Not yet |
| Totality / realizability | Exhaustive admitted-input totality | `realizable(candidate)` |
| Protected properties | Exhaustive relation implication | `valid(candidate -> requirement)` |
| Mutation and crossover | Typed formula edits | Whole-clause alternatives |
| Agent proposals | Digest-bound JSON formulas | Digest-bound JSON Tau formulas |
| Follow-up agent feedback | Replayed best attempt plus bounded counterexamples | Not yet |
| Semantic comparison | Complete table; added/removed behavior | Not yet |
| Counterexamples | Concrete assignments and dead-end inputs | Verdicts/diagnostics; no general temporal witness extraction |
| Replay | Entire deterministic evolution report | Rerun recorded queries with an external runtime |

Boolean syntax: identifiers, `true`, `false`, `!`, `&&`, `||`, `^`, `->`, `<->`, and parentheses. The project declares at most 12 Boolean input/output variables. This is a restricted reference language, not a parser for arbitrary Tau or `.zeno` files. Direct ZenoFCIS proof/code-generation integration is future work; the implementation currently follows functional-core/imperative-shell architecture.

## Using an LLM agent

```bash
python -m zeno_speccheck agent-request examples/authorization.json --out runs/request.json
# Give request.json to your agent; save its structured proposals as runs/proposals.json.
python -m zeno_speccheck evolve examples/authorization.json --proposals runs/proposals.json --out runs/assisted.json
```

The request contains the fixed project, its digest, and the Boolean seed's counterexamples. A response has exactly:

```json
{
  "schema": "zeno/proposals/v1",
  "project_digest": "COPY THE DIGEST FROM THE REQUEST",
  "proposals": [
    {"formula": "grant <-> authorized", "rationale": "Authorized requests must also be granted."}
  ]
}
```

For raw Tau, the response schema is `zeno/tau-proposals/v1`. Proposals are data; no code or shell command is evaluated. This is an agent-facing neurosymbolic workflow: an external LLM supplies hypotheses and the symbolic checker evaluates them. There is no bundled model, API key, autonomous LLM service, or claim that the evolutionary baseline itself is neural.

### Continue from a failed search

Instead of manually creating another numbered spec, give the agent the best attempt and its verified failures:

```bash
python -m zeno_speccheck evolve examples/deflationary_exit.json \
  --max-evaluations 256 --out runs/round1.json
# This illustrative budget intentionally returns exit 1: no candidate found.
python -m zeno_speccheck agent-request examples/deflationary_exit.json \
  --report runs/round1.json --max-witnesses 32 --out runs/next-request.json
# Give next-request.json to your agent; save its response to runs/proposals.json.
python -m zeno_speccheck evolve examples/deflationary_exit.json \
  --proposals runs/proposals.json --max-evaluations 512 --out runs/round2.json
python -m zeno_speccheck replay examples/deflationary_exit.json runs/round2.json
```

The follow-up command replays the **entire** prior Boolean search before emitting feedback. It rejects changed evidence, stale project digests, and reports from different source bytes. The request identifies the best passing candidate, or the best failed attempt when no candidate passed. It includes current failures and a bounded selection of historical witnesses, with explicit omitted counts. Historical witnesses may already be resolved by the target candidate. The next round still checks every candidate exhaustively; feedback truncation never weakens acceptance.

Keep each round's report for its lineage and full archive. A new round uses the same fixed project plus the supplied proposals; it does not automatically resume the prior population or merge archives. The agent/model remains external. Verified report feedback currently supports the finite Boolean profile; raw Tau still uses the initial project request and native check reports.

Project and proposal inputs are limited to 1 MB. Replay and follow-up commands accept reports up to 64 MB, using a bounded file read. Larger searches can produce reports over that limit; reduce the search budget or domain in a separately versioned project. Do not edit an old report to make it fit.

## Tau setup and use

Supply a Python interpreter that can import the **nanobind `tau` module**. A different package called `tau`, `tau-lang`, or `tau-ltl` is not automatically compatible. No Tau source or binary is bundled. Read the upstream license before installing or distributing Tau.

The tested source is `IDNI/tau-lang` commit `31b5b3cfa546d1769cb27c882f131a2914452b55`. See [the exact local build notes](docs/tau-runtime.md). The local validation build contained `sbf,tau`; bitvectors and Spot were absent. Full-LTL queries requiring Spot returned UNKNOWN.

```bash
python -m zeno_speccheck tau-evolve examples/tau_authorization.json \
  --tau-python /path/to/tau-venv/bin/python \
  --tau-source-revision 31b5b3cfa546d1769cb27c882f131a2914452b55 \
  --timeout 15 --out runs/tau.json

python -m zeno_speccheck tau-check examples/authorization.json \
  --formula 'grant <-> authorized' --algebra sbf \
  --tau-python /path/to/tau-venv/bin/python

ZENO_TAU_PYTHON=/path/to/tau-venv/bin/python \
  python -m unittest discover -s tests -v
```

If the module is not already on that interpreter's path, add `--tau-module-dir /path/to/build/bindings/python/nanobind`. A fresh worker owns each request, with a deadline and separate structured output. Native logging cannot be mistaken for a decision.

Raw Tau projects contain named protected requirements, a list of clause slots with variants, and a seed choosing one variant per slot. Mutations choose another variant; crossover recombines slots. Agent proposals may supply a whole replacement formula. The initial raw profile accepts complete formulas without definitions, declarations, comments, quoted constants, or REPL commands. Tau checks the actual syntax/types. Full language authoring and AST mutation are not yet supported.

The `sbf` exporter explicitly restricts Boolean inputs/outputs to `0` and `1`; it never treats all simple Boolean functions as a two-element domain. `bv[1]` export exists but was not live-tested in the reduced runtime. Atomless Boolean algebra claims cannot be certified by finite Boolean enumeration.

## Assurance and search limits

- Acceptance requires nonempty admitted inputs, an output for every admitted input, all protected requirements, and all configured examples. Determinism is required only when requested.
- Hard obligations cannot be exchanged for a smaller formula or a better fitness value. Search may use failed candidates as parents; only a passing candidate can be returned as `best_candidate`.
- Every finite candidate is checked exhaustively. Counterexamples guide selection and can be supplied to the next agent; this version does not implement a sample-only CEGIS acceleration.
- An empty search result says the configured budget did not find a candidate. It is not a proof that no solution exists.
- Tau's stream satisfiability has game semantics. Implication uses `valid(S -> P)` and a separate realizability gate. Missing dependencies, timeouts, and absent verdicts never pass.
- `approval: not_granted` is deliberate. Project hashes detect stale proposals/evidence; they do not authenticate a human or establish a signed approval workflow.

See [design and formal obligations](docs/design.md), [pilot results](evidence/pilot.json), [validation notes](docs/validation.md), [source lineage](docs/sources.md), and [next work](docs/roadmap.md).

Exit codes: `0` successful report/candidate, `1` failed obligation or exhausted search, `2` invalid input or inconclusive/unavailable backend.
