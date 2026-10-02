# Next work, gated by usefulness

Implemented: verified follow-up requests, persistent Boolean sessions with retained candidates and cumulative witnesses, and a standalone formula/English/decision-table review. The replayable exit-policy demo shows two evolutionary rounds followed by an externally authored simplification.

1. Import a real user-approved specification and independently written acceptance scenarios. Preserve its engine revision, types, warm-up semantics, assumptions, and known regressions. Measure how many human decisions and solver calls are saved against manual revision and simple enumeration.
2. Extend the existing review surface with concrete behavior questions and an explicit requirement-revision workflow. Add compact archival formats only when real sessions hit the current limits.
3. Expand typed Tau AST mutation only after an exact parser/API contract and conformance tests exist. Add temporal witnesses/counterstrategies when a trustworthy extraction interface is available.
4. Introduce learned proposal ranking only if it beats grammar-guided enumeration and the seeded evolutionary baseline on held-out tasks at fixed checking budgets. Freeze the oracle/requirements before measuring. A learned score never grants acceptance.
5. Add ZenoFCIS requirement/proof-obligation adapters at a pinned library revision. Verify generated Rust against approved contracts and record the refinement boundary.
6. Add reusable temporal contract families, incremental invalidation, and authenticated approval if users need maintained multi-agent projects.

Do not build a general autonomous formalization platform before the first real task shows a measured benefit. The present code is a narrow foundation for that test. Tau's expressiveness is not the only bound: search cost, available backends, specification quality, and review effort determine practical utility.
