"""Independent acceptance tests for semantic failure modes, not proof claims.

The small relation oracle below enumerates all 16 Boolean relations without
using the production expression evaluator to determine the expected verdict.
"""

import copy
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from zeno_speccheck.checking import check, semantic_diff
from zeno_speccheck.evolution import evolve, proposals
from zeno_speccheck.logic import mutations, parse
from zeno_speccheck.model import load_project, strict_json
from zeno_speccheck.tau import TauConfig, check_tau, formula_text, load_tau_project
from zeno_speccheck.tau_evolution import evolve_tau


def fixture(**changes):
    raw = {
        "schema": "zeno/boolean-project/v1",
        "name": "independent authorization fixture",
        "inputs": ["authorized"],
        "outputs": ["grant"],
        "assumption": "true",
        "requirements": [{
            "id": "decision",
            "english": "Grant exactly when authorized.",
            "formula": "grant <-> authorized",
        }],
        "seed": "grant -> authorized",
    }
    raw.update(changes)
    return raw


def relation_source(mask):
    terms = []
    for index, (authorized, grant) in enumerate(itertools.product((False, True), repeat=2)):
        if mask & (1 << index):
            a = "authorized" if authorized else "!authorized"
            g = "grant" if grant else "!grant"
            terms.append(f"({a} && {g})")
    return " || ".join(terms) or "false"


def proposal_packet(project, *formulas):
    return {
        "schema": "zeno/proposals/v1",
        "project_digest": project.identity,
        "proposals": [{"formula": formula, "rationale": "test proposal"} for formula in formulas],
    }


class ExhaustiveSemanticAcceptance(unittest.TestCase):
    def test_all_sixteen_relations_against_independent_exact_oracle(self):
        project = load_project(fixture())
        for mask in range(16):
            with self.subTest(mask=mask):
                report = check(project, parse(relation_source(mask), project.variables))
                # Only (False, False) and (True, True) implement the required
                # total relation: bits 0 and 3 in the independently defined table.
                self.assertEqual(report["status"] == "pass", mask == 0b1001)

    def test_all_relations_against_independent_nondeterministic_oracle(self):
        requirements = [{"id": "safety", "english": "Grant requires authorization.",
                         "formula": "grant -> authorized"}]
        for deterministic in (False, True):
            project = load_project(fixture(requirements=requirements, deterministic=deterministic))
            allowed_masks = {0b0101, 0b1001} if deterministic else {0b0101, 0b1001, 0b1101}
            for mask in range(16):
                with self.subTest(deterministic=deterministic, mask=mask):
                    report = check(project, parse(relation_source(mask), project.variables))
                    self.assertEqual(report["status"] == "pass", mask in allowed_masks)

    def test_always_deny_has_a_concrete_positive_obligation_witness(self):
        project = load_project(fixture())
        report = check(project, parse("!grant", project.variables))
        self.assertEqual(report["status"], "fail")
        self.assertIn({"kind": "forbidden_behavior", "requirement": "decision",
                       "values": {"authorized": True, "grant": False}}, report["violations"])

    def test_false_spec_cannot_pass_by_vacuous_entailment(self):
        project = load_project(fixture())
        report = check(project, parse("false", project.variables))
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["permitted_pairs"], 0)
        self.assertEqual({tuple(v["inputs"].items()) for v in report["violations"]
                          if v["kind"] == "dead_end_input"},
                         {(("authorized", False),), (("authorized", True),)})

    def test_empty_domain_does_not_pass(self):
        project = load_project(fixture(assumption="false"))
        report = check(project, parse("true", project.variables))
        self.assertEqual(report["status"], "fail")
        self.assertIn({"kind": "empty_input_domain"}, report["violations"])

    def test_dead_end_on_only_one_admitted_input_is_rejected(self):
        project = load_project(fixture())
        report = check(project, parse("authorized && grant", project.variables))
        self.assertIn({"kind": "dead_end_input", "inputs": {"authorized": False}},
                      report["violations"])

    def test_valid_nondeterminism_is_reported_without_inventing_a_policy(self):
        requirements = [{"id": "safety", "english": "Grant requires authorization.",
                         "formula": "grant -> authorized"}]
        project = load_project(fixture(requirements=requirements))
        report = check(project, parse("grant -> authorized", project.variables))
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["inputs_with_multiple_outputs"], 1)
        self.assertEqual(report["permitted_pairs"], 3)
        # The fixed requirements genuinely permit denial: adequacy is not inferred.
        self.assertEqual(check(project, parse("!grant", project.variables))["status"], "pass")
        self.assertEqual(report["approval"], "not_granted")

    def test_semantic_diff_exposes_extra_permitted_output(self):
        project = load_project(fixture())
        exact = parse("grant <-> authorized", project.variables)
        weak = parse("grant -> authorized", project.variables)
        diff = semantic_diff(project, exact, weak)
        self.assertFalse(diff["equivalent"])
        self.assertEqual(diff["newly_permitted"], [{"authorized": True, "grant": False}])
        self.assertEqual(diff["newly_forbidden"], [])

    def test_equivalence_is_scoped_to_the_frozen_domain(self):
        project = load_project(fixture(assumption="authorized"))
        a = check(project, parse("grant", project.variables))
        b = check(project, parse("grant || !authorized", project.variables))
        self.assertEqual(a["semantic_digest"], b["semantic_digest"])
        expanded = load_project(fixture())
        c = check(expanded, parse("grant", expanded.variables))
        self.assertNotEqual(a["semantic_digest"], c["semantic_digest"])


class FrozenInputsAndUntrustedProposals(unittest.TestCase):
    def test_output_cannot_control_input_assumption(self):
        with self.assertRaises(ValueError):
            load_project(fixture(assumption="grant"))

    def test_variable_overlap_duplicate_and_unknown_names_are_rejected(self):
        for inputs, outputs in [(["authorized"], ["authorized"]),
                                (["authorized", "authorized"], ["grant"]),
                                (["true"], ["grant"])]:
            with self.subTest(inputs=inputs, outputs=outputs), self.assertRaises(ValueError):
                load_project(fixture(inputs=inputs, outputs=outputs))
        project = load_project(fixture())
        with self.assertRaises(ValueError):
            check(project, parse("unknown"))

    def test_proposals_cannot_rewrite_the_frozen_project_or_claim_approval(self):
        project = load_project(fixture())
        for extra in ({"requirements": []}, {"assumption": "false"},
                      {"outputs": []}, {"approval": "granted"}):
            packet = proposal_packet(project, "true")
            packet.update(extra)
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                proposals(project, packet)

    def test_proposal_cannot_supply_its_own_check_verdict(self):
        project = load_project(fixture())
        packet = proposal_packet(project, "false")
        packet["proposals"][0]["status"] = "pass"
        with self.assertRaises(ValueError):
            proposals(project, packet)

    def test_stale_project_digest_is_rejected(self):
        project = load_project(fixture())
        packet = proposal_packet(project, "grant <-> authorized")
        changed = fixture()
        changed["requirements"][0]["formula"] = "grant -> authorized"
        with self.assertRaises(ValueError):
            proposals(load_project(changed), packet)

    def test_unknown_schema_and_duplicate_json_keys_are_rejected(self):
        project = load_project(fixture())
        packet = proposal_packet(project, "true")
        packet["schema"] = "zeno/proposals/v999"
        with self.assertRaises(ValueError):
            proposals(project, packet)
        for source in ('{"assumption":"true","assumption":"false"}',
                       '{"verdict":NaN}', '{"verdict":Infinity}'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                strict_json(source)

    def test_raw_code_temporal_and_arithmetic_syntax_are_rejected(self):
        project = load_project(fixture())
        for source in ('print("unexpected")', 'grant; true', 'authorized.__class__',
                       'grant = authorized', 'G(grant)', 'grant + authorized',
                       'grant[t]', 'grant or authorized'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                proposals(project, proposal_packet(project, source))

    def test_examples_require_real_booleans_and_cannot_smuggle_scope_changes(self):
        for example in (
            {"id": "bad", "values": {"authorized": 1, "grant": True}, "allowed": True},
            {"id": "bad", "values": {"authorized": False, "grant": True}, "allowed": True},
        ):
            with self.subTest(example=example), self.assertRaises(ValueError):
                load_project(fixture(examples=[example]))


class EvolutionAcceptance(unittest.TestCase):
    def test_valid_candidate_beats_smaller_invalid_candidates(self):
        project = load_project(fixture(seed="false"))
        result = evolve(project, generations=0, proposal_data=proposal_packet(
            project, "true", "!grant", "grant <-> authorized"))
        self.assertEqual(result["status"], "candidate_found")
        self.assertEqual(result["best_candidate"]["check"]["status"], "pass")
        self.assertEqual(result["best_candidate"]["check"]["permitted_pairs"], 2)
        self.assertEqual(result["approval"], "not_granted")
        self.assertTrue(result["counterexamples"])

    def test_insufficient_search_budget_is_not_a_proof_of_impossibility(self):
        project = load_project(fixture(seed="false"))
        result = evolve(project, max_evaluations=1)
        self.assertEqual(result["status"], "no_candidate_found")
        self.assertIsNone(result["best_candidate"])
        self.assertEqual(result["best_attempt"]["check"]["status"], "fail")
        self.assertTrue(any("does not establish impossibility" in text for text in result["limitations"]))

    def test_seeded_runs_replay_exactly_and_do_not_mutate_proposals(self):
        project = load_project(fixture())
        packet = proposal_packet(project, "grant <-> authorized", "!(grant ^ authorized)")
        before = copy.deepcopy(packet)
        options = {"seed": 73, "generations": 3, "population": 4,
                   "max_evaluations": 40, "proposal_data": packet}
        first, second = evolve(project, **options), evolve(project, **options)
        self.assertEqual(first, second)
        self.assertEqual(packet, before)
        self.assertGreater(first["equivalent_candidates"], 0)

    def test_equivalent_proposals_share_complete_behavior_identity(self):
        project = load_project(fixture(seed="false"))
        result = evolve(project, generations=0, proposal_data=proposal_packet(
            project, "grant <-> authorized", "!(grant ^ authorized)"))
        proposals_only = [r for r in result["candidates"] if r["origin"] == "agent_proposal"]
        self.assertEqual(proposals_only[0]["check"]["semantic_digest"],
                         proposals_only[1]["check"]["semantic_digest"])
        self.assertEqual(proposals_only[1]["equivalent_to"], proposals_only[0]["id"])

    def test_counterexample_archive_references_real_failed_candidates(self):
        project = load_project(fixture())
        result = evolve(project, seed=4, generations=2, max_evaluations=30)
        by_id = {record["id"]: record for record in result["candidates"]}
        self.assertTrue(result["counterexamples"])
        for entry in result["counterexamples"]:
            original = by_id[entry["first_candidate"]]
            self.assertIn(entry["witness"], original["check"]["violations"])
            witness = entry["witness"]
            if witness["kind"] == "forbidden_behavior":
                values = witness["values"]
                self.assertNotEqual(values["authorized"], values["grant"])

    def test_typed_mutation_can_generate_the_required_strengthening(self):
        project = load_project(fixture())
        mutants = mutations(project.seed, project.variables)
        self.assertTrue(any(check(project, mutant)["status"] == "pass" for mutant in mutants))
        self.assertTrue(all(mutant.variables() <= set(project.variables) for mutant in mutants))

    def test_boolean_values_cannot_masquerade_as_numeric_search_budgets(self):
        project = load_project(fixture())
        for option in ("seed", "generations", "population", "max_evaluations"):
            with self.subTest(option=option), self.assertRaises(ValueError):
                evolve(project, **{option: True})


class TauBoundaryAcceptance(unittest.TestCase):
    @staticmethod
    def raw_project():
        return {
            "schema": "zeno/tau-project/v1",
            "name": "minimal raw Tau fixture",
            "requirements": [{"id": "law", "english": "A protected law.", "formula": "T"}],
            "clauses": [{"id": "slot", "variants": ["T", "F"]}],
            "seed": [0],
        }

    @contextmanager
    def fake_backend(self, expression, errors="[]"):
        # This stub exercises the actual worker process and result transport.
        # It is deliberately not evidence about the real Tau decision engine.
        source = f'''class Report:
    errors = {errors}
    def __str__(self):
        return "controlled test report"
class Response:
    value = {expression}
    report = Report()
def reset():
    pass
def valid(formula):
    return Response()
def realizable(formula):
    return Response()
'''
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, "tau.py").write_text(source, encoding="utf-8")
            yield TauConfig(module_dir=temporary, timeout=5)

    def fake_backend_result(self, expression, errors="[]"):
        with self.fake_backend(expression, errors) as config:
            return check_tau("T", [{"id": "law", "formula": "T"}], config)

    def test_missing_backend_does_not_produce_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = TauConfig(python=str(Path(temporary, "absent-python")))
            report = check_tau("T", [], config)
        self.assertEqual(report["status"], "backend_error")
        self.assertEqual(report["approval"], "not_granted")

    def test_false_backend_verdict_is_distinct_from_unknown(self):
        self.assertEqual(self.fake_backend_result("False")["status"], "fail")
        self.assertEqual(self.fake_backend_result("None")["status"], "unknown")

    def test_backend_error_cannot_be_hidden_behind_a_true_value(self):
        report = self.fake_backend_result("True", '["controlled backend failure"]')
        self.assertNotEqual(report["status"], "pass")

    def test_non_boolean_backend_value_is_rejected(self):
        self.assertEqual(self.fake_backend_result("'true'")["status"], "backend_error")

    def test_worker_timeout_is_unknown_not_false_or_pass(self):
        source = '''import time
def reset():
    pass
def valid(formula):
    time.sleep(5)
def realizable(formula):
    time.sleep(5)
'''
        with tempfile.TemporaryDirectory() as temporary:
            Path(temporary, "tau.py").write_text(source, encoding="utf-8")
            report = check_tau("T", [], TauConfig(module_dir=temporary, timeout=0.1))
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["backend"]["reason"], "worker_timeout")

    def test_requirements_cannot_be_replaced_by_clause_slots(self):
        raw = self.raw_project()
        raw["requirements"] = [{"id": "law", "variants": ["T"]}]
        with self.assertRaises(ValueError):
            load_tau_project(raw)

    def test_clauses_cannot_be_replaced_by_requirement_objects(self):
        raw = self.raw_project()
        raw["clauses"] = [{"id": "slot", "english": "wrong shape", "formula": "T"}]
        with self.assertRaises(ValueError):
            load_tau_project(raw)

    def test_multiple_tau_commands_are_rejected(self):
        for source in ("T. run T.", "T; F", "T\x00"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                formula_text(source)

    def test_tau_formula_must_remain_nonempty_after_terminator_removal(self):
        with self.assertRaises(ValueError):
            formula_text(".")

    def test_tau_formula_fragment_cannot_escape_composition_parentheses(self):
        for source in ("F) || (T", "(T", "T)"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                formula_text(source)

    def test_unknown_tau_candidates_cannot_win_evolution(self):
        with self.fake_backend("None") as config:
            report = evolve_tau(self.raw_project(), config, max_evaluations=2)
        self.assertEqual(report["status"], "inconclusive")
        self.assertIsNone(report["best_candidate"])
        self.assertTrue(all(record["check"]["status"] == "unknown" for record in report["candidates"]))

    def test_missing_backend_stops_raw_search_without_claiming_impossibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = TauConfig(python=str(Path(temporary, "absent-python")))
            report = evolve_tau(self.raw_project(), config)
        self.assertEqual(report["status"], "inconclusive")
        self.assertIsNone(report["best_candidate"])
        self.assertEqual(report["evaluated_candidates"], 1)


class CliReplayAcceptance(unittest.TestCase):
    def test_replay_recomputes_report_and_detects_modified_approval(self):
        from zeno_speccheck.cli import main

        with tempfile.TemporaryDirectory() as temporary:
            project_path = Path(temporary, "project.json")
            report_path = Path(temporary, "report.json")
            replay_path = Path(temporary, "replay.json")
            project_path.write_text(json.dumps(fixture(seed="grant <-> authorized")), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["evolve", str(project_path), "--generations", "0",
                                       "--out", str(report_path)]), 0)
                self.assertEqual(main(["replay", str(project_path), str(report_path),
                                       "--out", str(replay_path)]), 0)
            self.assertEqual(json.loads(replay_path.read_text())["status"], "pass")
            tampered = json.loads(report_path.read_text())
            tampered["approval"] = "granted"
            report_path.write_text(json.dumps(tampered), encoding="utf-8")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["replay", str(project_path), str(report_path),
                                       "--out", str(replay_path)]), 1)
            self.assertEqual(json.loads(replay_path.read_text())["status"], "fail")

    def test_non_object_replay_report_is_structured_invalid(self):
        from zeno_speccheck.cli import main

        with tempfile.TemporaryDirectory() as temporary:
            project_path = Path(temporary, "project.json")
            report_path = Path(temporary, "report.json")
            project_path.write_text(json.dumps(fixture()), encoding="utf-8")
            report_path.write_text("[]", encoding="utf-8")
            errors = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                self.assertEqual(main(["replay", str(project_path), str(report_path)]), 2)
            self.assertEqual(json.loads(errors.getvalue())["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
