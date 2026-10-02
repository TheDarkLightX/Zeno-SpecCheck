"""End-to-end continuation with independent behavior and provenance controls."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from zeno_speccheck.cli import main, source_digest
from zeno_speccheck.evolution import evolve
from zeno_speccheck.feedback import replay_boolean, verified_feedback
from zeno_speccheck.model import load_project, read_json


ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "examples/authorization.json"
EXIT = ROOT / "examples/deflationary_exit.json"


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.project = load_project(read_json(AUTH))
        self.report = evolve(self.project, generations=0)
        self.source = source_digest()
        self.report["tool"] = {"source_digest": self.source}

    def test_verified_feedback_contains_actual_target_failures_without_approval(self):
        original = copy.deepcopy(self.report)
        feedback = verified_feedback(self.project, self.report, self.source)
        self.assertEqual(feedback["replay"]["status"], "pass")
        self.assertEqual(feedback["search_status"], "no_candidate_found")
        self.assertEqual(feedback["target_check"]["status"], "fail")
        witness = {"kind": "forbidden_behavior", "requirement": "AUTH-1",
                   "values": {"authorized": True, "grant": False}}
        self.assertIn(witness, feedback["counterexamples"])
        self.assertEqual(feedback["approval"], "not_granted")
        self.assertEqual(self.report, original)

    def test_tampered_evidence_cannot_become_agent_feedback(self):
        for field, value in (("approval", "granted"), ("counterexamples", []),
                             ("status", "candidate_found")):
            report = copy.deepcopy(self.report)
            report[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "replay failed"):
                verified_feedback(self.project, report, self.source)

    def test_replay_distinguishes_boolean_from_integer_and_float(self):
        for value in (True, 1.0):
            report = copy.deepcopy(self.report)
            report["evaluated_candidates"] = value
            with self.subTest(value=value):
                self.assertEqual(replay_boolean(self.project, report, self.source)["status"], "fail")

    def test_stale_project_or_source_cannot_supply_feedback(self):
        for field, value in (("project_digest", "stale"), ("tool", {"source_digest": "stale"})):
            report = copy.deepcopy(self.report)
            report[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verified_feedback(self.project, report, self.source)

    def test_malformed_provenance_or_search_is_invalid(self):
        for field in ("tool", "search"):
            for value in (None, [], 1, "unexpected"):
                report = copy.deepcopy(self.report)
                report[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replay_boolean(self.project, report, self.source)

    def test_feedback_limit_is_explicit_and_does_not_change_full_acceptance(self):
        feedback = verified_feedback(self.project, self.report, self.source, max_witnesses=1)
        self.assertEqual(len(feedback["counterexamples"]), 1)
        self.assertGreater(feedback["witnesses_omitted"], 0)
        self.assertGreater(feedback["target_check"]["violations_omitted"], 0)
        self.assertEqual(feedback["target_check"]["status"], "fail")
        for limit in (0, True, 257):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                verified_feedback(self.project, self.report, self.source, max_witnesses=limit)

    def test_passing_target_remains_passing_with_historical_failures(self):
        report = evolve(self.project, max_evaluations=64)
        report["tool"] = {"source_digest": self.source}
        feedback = verified_feedback(self.project, report, self.source)
        self.assertEqual(feedback["target_check"]["status"], "pass")
        self.assertEqual(feedback["target_check"]["violation_count"], 0)
        self.assertTrue(feedback["counterexamples"])


class FeedbackWorkflowTests(unittest.TestCase):
    def test_failed_search_then_agent_proposal_then_verified_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            report, request, proposals, repaired, replay = (
                Path(directory, name + ".json") for name in
                ("round1", "request", "proposals", "round2", "replay"))
            self.assertEqual(main(["evolve", str(AUTH), "--generations", "0", "--out", str(report)]), 1)
            self.assertEqual(main(["agent-request", str(AUTH), "--report", str(report),
                                   "--out", str(request)]), 0)
            packet = read_json(request)
            self.assertEqual(packet["project"], read_json(AUTH))
            self.assertEqual(packet["feedback"]["target_check"]["status"], "fail")
            # A controlled external proposal, not a claim that a neural model ran.
            proposals.write_text(json.dumps({"schema": packet["response_schema"],
                "project_digest": packet["project_digest"], "proposals": [
                    {"formula": "grant <-> authorized", "rationale": "Also grant authorized requests."}]}))
            self.assertEqual(main(["evolve", str(AUTH), "--generations", "0", "--proposals", str(proposals),
                                   "--out", str(repaired)]), 0)
            self.assertEqual(main(["replay", str(AUTH), str(repaired), "--out", str(replay)]), 0)
            result = read_json(repaired)
            self.assertEqual(result["best_candidate"]["origin"], "agent_proposal")
            self.assertEqual(result["best_candidate"]["check"]["permitted_pairs"], 2)
            self.assertEqual(result["approval"], "not_granted")

    def test_documented_large_report_replays_and_supplies_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            report, replay, request = (Path(directory, name + ".json") for name in ("report", "replay", "request"))
            self.assertEqual(main(["evolve", str(EXIT), "--max-evaluations", "512", "--out", str(report)]), 0)
            self.assertGreater(report.stat().st_size, 1_000_000)
            self.assertEqual(main(["replay", str(EXIT), str(report), "--out", str(replay)]), 0)
            self.assertEqual(main(["agent-request", str(EXIT), "--report", str(report), "--out", str(request)]), 0)
            self.assertEqual(read_json(request)["feedback"]["target_check"]["status"], "pass")

    def test_malformed_report_produces_structured_cli_error(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory, "bad.json")
            report.write_text(json.dumps({"schema": "zeno/evolution-report/v1",
                "project_digest": load_project(read_json(AUTH)).identity, "tool": []}))
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                self.assertEqual(main(["agent-request", str(AUTH), "--report", str(report)]), 2)
            self.assertEqual(json.loads(error.getvalue())["status"], "invalid")

    def test_project_and_proposal_limit_remains_smaller_than_report_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            oversized = Path(directory, "input.json")
            oversized.write_text('"' + "x" * 1_000_000 + '"')
            with self.assertRaisesRegex(ValueError, "exceeds 1000000 bytes"):
                read_json(oversized)
            with self.assertRaisesRegex(ValueError, "exceeds 16 bytes"):
                read_json(oversized, max_bytes=16)


if __name__ == "__main__":
    unittest.main()
