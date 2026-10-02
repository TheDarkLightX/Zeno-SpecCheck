# Design and obligations

## Boundary

Version 0.2 is a specification-analysis tool. It proposes candidates; it does not deploy a controller, authorize a requirements change, or certify complete intent. The Python reference checker is an implementation of finite semantics, not a formally verified theorem prover. Independent bit-mask tests and a real Tau differential comparison provide scoped evidence about it.

`logic.py`, the immutable project model, `checking.py`, Boolean `evolution.py`, `feedback.py`, `session.py`, and `review.py` form the core. The CLI, the JSON file reader in `model.py`, and the Tau process bridge are the imperative shell. Search, feedback, session verification, and HTML rendering perform no file/process operations. Search receives immutable Boolean projects. Raw Tau projects are copied and strictly validated before search.

## Finite relation semantics

Let X and Y be the declared Boolean input/output spaces, A(x) a fixed input assumption, S(x,y) a candidate, and R_j(x,y) protected requirements. Acceptance requires:

1. Domain non-vacuity: ∃x ∈ X. A(x).
2. Totality: ∀x ∈ X. A(x) ⇒ ∃y ∈ Y. S(x,y).
3. Requirement refinement: ∀j,x,y. A(x) ∧ S(x,y) ⇒ R_j(x,y).
4. Positive examples belong to S; negative examples do not.
5. If requested, ∀x,y₁,y₂. A(x) ∧ S(x,y₁) ∧ S(x,y₂) ⇒ y₁=y₂.

Assumptions may mention inputs only. Examples outside A are rejected as invalid configuration. Positive examples contradicting a requirement are rejected. General contradictions among requirements become failed candidate obligations, rather than an invented repair of the requirements.

Refinement permits excluding some requirement-permitted outputs. Supply positive examples or more precise requirements if those outputs must remain possible. The checker cannot infer missing requirements from English; the English string is displayed alongside the authoritative formula.

Complete truth tables define semantic identity under the fixed project digest. Comparisons never reuse a signature across another variable order, assumption, or requirement revision. Evolution ranks by number of failed obligations, AST size, and canonical spelling; only zero-failure candidates are eligible as results. Typed edits and conjunction/disjunction crossover retain explicit parent identities. Selection keeps one representative per encountered behavior table.

All generated candidates are exhaustively evaluated within the declared domain. The counterexample archive is an evidence and agent-feedback channel, not a proof that incomplete sample-based learning converges. The implementation has bounded stochastic search and no completeness guarantee.

## Iterative agent feedback

A follow-up request takes a saved Boolean evolution report. Replay recomputes the full search using its seed, bounds and strictly validated proposals, then compares canonical JSON digests of every report field except the tool envelope. Unlike Python object equality, this distinguishes `true`, `1`, and `1.0`. The source digest must match the running package, and the project digest must match the fixed project.

Only a replayed report supplies feedback. The target is the best passing candidate if one exists, otherwise the best attempt. The feedback contains current failures and diverse historical obligation witnesses, bounded by an explicit count. Omitted counts and the full archive digest identify the scope of that selection. The full archive remains in the round's report; the feedback subset is not a replacement acceptance oracle.

Replay detects inconsistent evidence, not authorship. A party able to produce a different, internally consistent search report can supply it; no signature-based provenance or human approval is implied. Standalone `evolve` starts an independent search. Sessions add verified retention across rounds.

## Multi-round sessions

A session contains every complete round report, a digest link to the preceding round, cumulative diagnostic witnesses, and the best candidate across all rounds. Each continuation verifies all prior rounds before selecting up to `population` representatives of distinct behavior tables, ranked by violations, size, and canonical spelling. These formulas become a warm start; the frozen project seed remains unchanged. Their previous verdicts are not reused: they are rechecked and count against the new budget. Retention preserves an earlier winner even if a later round exhausts its budget without success.

The session replay regenerates retention from regenerated earlier evidence, rather than trusting the saved warm-start list. It compares round order, parent links, all candidate evidence, witness origins, global selection, and the session summary. Source and project changes invalidate continuation. This is continuation with retained candidates and explicit new random seeds; it is not checkpointing a random generator mid-generation. The 16-round and 8,192-total-requested-evaluation limits bound session growth; verification adds work beyond those search counts.

Review replays a session before rendering. It computes behavior changes directly from the seed and selected formulas. The displayed decision table is capped at 64 admitted inputs with explicit omissions; acceptance and semantic comparison still cover the complete domain. All project/formula text is HTML-escaped, and the standalone view has no scripts or external dependencies. A view does not grant approval or independently prove a Tau claim.

## Tau semantics

Realizability is existence of a causal output strategy satisfying S for all input traces. It is different from existence of one compatible trace. Property implication uses Tau's universal trace validity API; it must not use the negation of game realizability of S ∧ ¬R.

Each raw clause remains intact, and the candidate is a parenthesized conjunction of those clauses. Source-level initialization/lookback effects remain Tau's responsibility; the application does not simplify tautologies or claim syntax-normalization equivalence. Raw search does not claim semantic deduplication.

The result protocol reads `result.value`, never `bool(result)` as the verdict. Native errors erase a purported Boolean answer. All required queries must return clean True values before a pass. The source revision is caller-declared; module bytes are independently hashed. Neither is an independent proof certificate.

## Decisive controls and nonclaims

`tests/test_adversarial.py` independently enumerates all 16 relations on one Boolean input/output pair under exact, nondeterministic and deterministic requirements. It checks contradictory domains/specs, dead-end inputs, always-deny, stale or scope-changing proposals, equivalent mutations, and complete replay. Transport tests use explicitly fake modules; these are not Tau correctness tests.

`tests/test_tau_live.py` executes real Tau when enabled. It compares all 16 relations against the finite checker through the restricted sbf exporter, exercises the complete four-candidate raw evolution, checks parse failure, and distinguishes trace validity from causal realizability.

The actual live build lacks cvc5 and Spot. Bitvector export and arbitrary full-LTL synthesis remain unvalidated here. A sampled trace is never promoted to an all-traces guarantee. This release does not implement infinite-state invariant inference, automatic arithmetic synthesis, neural training, ZenoFCIS code generation, or signature-based approval.
