"""Optional real-engine tests. Never replace these with a mock and claim Tau ran."""

from itertools import product
import os
from pathlib import Path
import unittest

from zeno_speccheck.checking import check
from zeno_speccheck.logic import parse
from zeno_speccheck.model import load_project, read_json
from zeno_speccheck.tau import PINNED_TAU, TauConfig, check_tau, export_tau, run_queries
from zeno_speccheck.tau_evolution import evolve_tau


@unittest.skipUnless(os.environ.get("ZENO_TAU_PYTHON"), "set ZENO_TAU_PYTHON to enable real Tau tests")
class TauLiveTests(unittest.TestCase):
    def setUp(self):
        self.config = TauConfig(os.environ["ZENO_TAU_PYTHON"], os.environ.get("ZENO_TAU_MODULE_DIR"),
                                15, os.environ.get("ZENO_TAU_REVISION"))
        self.root = Path(__file__).resolve().parents[1]

    def test_actual_clause_evolution_keeps_all_hard_gates(self):
        project = read_json(self.root / "examples/tau_authorization.json")
        result = evolve_tau(project, self.config)
        self.assertEqual(result["status"], "candidate_found")
        verdicts = {r["genome"][0]: r["check"]["status"] for r in result["candidates"]}
        self.assertEqual(verdicts, {0: "fail", 1: "pass", 2: "fail", 3: "fail"})
        for record in result["candidates"]:
            self.assertEqual(len(record["check"]["backend"]["runtime"]["module_sha256"]), 64)

    def test_all_sixteen_boolean_relations_agree_with_tau_translation(self):
        raw = read_json(self.root / "examples/authorization.json")
        # Only the relation property and totality are cross-checked here.
        raw["examples"] = []
        raw["deterministic"] = False
        project = load_project(raw)
        for mask in range(16):
            clauses = []
            for bit, (a, g) in enumerate(product((False, True), repeat=2)):
                if mask & (1 << bit):
                    clauses.append(f"({'authorized' if a else '!authorized'} && {'grant' if g else '!grant'})")
            expr = parse(" || ".join(clauses) or "false")
            exported = export_tau(project, expr, "sbf")
            result = check_tau(exported["formula"], exported["requirements"], self.config)
            with self.subTest(mask=mask):
                self.assertEqual(result["status"], check(project, expr)["status"], result)

    def test_stream_implication_is_not_realizability_of_a_violation(self):
        result = run_queries([
            {"id": "implication", "operation": "valid", "formula": "T -> (i1[t]:sbf = 0:sbf)."},
            {"id": "violation-strategy", "operation": "realizable", "formula": "i1[t]:sbf != 0:sbf."},
        ], self.config)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([q["value"] for q in result["queries"]], [False, False])

    def test_parse_failure_cannot_pass(self):
        result = check_tau("nonsense nonsense", [], self.config)
        self.assertNotEqual(result["status"], "pass")
        self.assertIsNone(result["backend"]["queries"][0]["value"])


if __name__ == "__main__":
    unittest.main()
