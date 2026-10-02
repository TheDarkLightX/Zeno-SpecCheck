# Working on Zeno-SpecCheck

- Keep requirement/assumption changes explicit and versioned. Candidate proposals cannot change the frozen project or claim approval.
- Keep the finite relation core pure. File/process effects belong in the CLI and Tau adapter.
- Preserve TRUE, FALSE, UNKNOWN, malformed input, and backend failure distinctions. Never accept a timeout or absent verdict.
- Tau `valid(S -> R)` and `realizable(S)` are separate gates. Stream-aware `unsat(S && !R)` is not a substitute for entailment.
- Preserve the chosen algebra and time model. Finite Boolean tests prove nothing about unrestricted atomless Boolean algebra or temporal liveness.
- Add meaningful semantic controls for assurance changes. Run `python -m unittest discover -s tests -v`; live tests require `ZENO_TAU_PYTHON` and must not be reported as run when skipped.
- Use a held-out task set before claiming learned search improves on enumeration or evolution. Report exhausted searches and negative results.
- Do not vendor Tau binaries/source or copy private research into this public repository. Record primary-source provenance and external runtime hashes.
