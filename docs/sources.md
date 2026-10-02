# Source ledger

Inspected 2026-10-02. This public implementation was written independently; no private repository code, findings, or specifications were copied.

- [Verus spec-check](https://github.com/verus-lang/verus-spec-check): inspiration for exercising specifications and finding contracts that fail to distinguish faulty implementations. The current implementation here evolves candidate specifications; it does not run Verus or copy its implementation.
- [Tau source, pinned](https://github.com/IDNI/tau-lang/tree/31b5b3cfa546d1769cb27c882f131a2914452b55): README stream semantics; `src/api.h`; `bindings/python/nanobind/tau_nanobind.cpp`; `tests/bindings/python/test_decision_api.py`.
- [Tau result contract](https://github.com/IDNI/tau-lang/blob/31b5b3cfa546d1769cb27c882f131a2914452b55/docs/tau_result.md): Boolean values versus absent verdicts, errors and diagnostics.
- [Tau license](https://github.com/IDNI/tau-lang/blob/31b5b3cfa546d1769cb27c882f131a2914452b55/LICENSE.md): optional external runtime; not redistributed here.
- [A Theory of Mutations with Applications to Vacuity, Coverage, and Fault Tolerance](https://people.eecs.berkeley.edu/~sseshia/pubs/b2hd-kupferman-fmcad08.html), Kupferman, Li, Seshia, FMCAD 2008: prior work connecting mutation and specification adequacy.
- [Validating the Correctness of Reactive Systems Specifications Through Systematic Exploration](https://smlab.cs.tau.ac.il/syntech/validate/index.html), Ma'ayan, Maoz, Rozi, MODELS 2022: prior work on exploring reactive requirements. This is Spectra/Syntech at Tel Aviv University, unrelated to Tau Lang.

No priority claim is made for evolutionary specification repair, CEGIS, mutation testing, or neuro-symbolic synthesis. The contribution pursued here is a usable integration of fixed intent, agent proposals, revision identities, independent finite evidence, and Tau's native decision procedures.
