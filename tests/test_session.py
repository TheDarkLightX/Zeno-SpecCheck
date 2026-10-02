"""Semantic acceptance controls for retained search and human review."""

import copy
from itertools import product
import json
from pathlib import Path
import tempfile
import unittest

from zeno_speccheck.cli import main
from zeno_speccheck.evolution import evolve
from zeno_speccheck.logic import parse
from zeno_speccheck.model import digest, load_project, read_json
from zeno_speccheck.review import render_html, review_session
from zeno_speccheck.session import evolve_session, replay_session, session_feedback


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "examples/deflationary_exit.json"


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = load_project(read_json(PROJECT))
        cls.first = evolve_session(cls.project, "test-source", seed=0, max_evaluations=64)
        cls.second = evolve_session(cls.project, "test-source", previous=cls.first, seed=1, max_evaluations=128)

    def test_retained_search_repairs_all_thirty_two_assignments(self):
        self.assertEqual(self.first["status"], "no_candidate_found")
        self.assertEqual(self.second["status"], "candidate_found")
        candidate = parse(self.second["best_candidate"]["check"]["formula"])
        for holding, profit, exit_signal, sell, next_hold in product((False, True), repeat=5):
            expected_sell = holding and (profit or exit_signal)
            expected_hold = holding and not expected_sell
            row = dict(holding=holding, profit=profit, exit=exit_signal, sell=sell, hold_next=next_hold)
            self.assertEqual(candidate.evaluate(row), sell == expected_sell and next_hold == expected_hold)
        self.assertEqual(self.second["evaluated_candidates"], 192)
        self.assertLess(self.second["unique_candidates"], 192)

    def test_previous_population_and_witnesses_are_preserved_without_mutation(self):
        before = digest(self.first)
        replay = evolve_session(self.project, "test-source", previous=self.first, seed=1, max_evaluations=128)
        self.assertEqual(digest(self.first), before)
        self.assertEqual(replay, self.second)
        self.assertTrue(replay["rounds"][1]["report"]["warm_start"])
        self.assertTrue(any(c["origin"] == "retained_candidate" for c in replay["rounds"][1]["report"]["candidates"]))
        old_witnesses = {digest(w["witness"]) for w in self.first["counterexamples"]}
        self.assertLessEqual(old_witnesses, {digest(w["witness"]) for w in replay["counterexamples"]})
        for entry in replay["counterexamples"]:
            source = replay["rounds"][entry["first_round"] - 1]["report"]
            origin = next(c for c in source["candidates"] if c["id"] == entry["first_candidate"])
            self.assertIn(entry["witness"], origin["check"]["violations"])

    def test_all_rounds_replay_and_altered_history_cannot_resume(self):
        self.assertEqual(replay_session(self.project, self.second, "test-source")["status"], "pass")
        for mutation in ("lineage", "retention", "witness", "approval", "winner", "order"):
            changed = copy.deepcopy(self.second)
            if mutation == "lineage":
                changed["rounds"][1]["previous_round_digest"] = "stale"
            elif mutation == "retention":
                changed["rounds"][1]["report"]["warm_start"] = ["false"]
            elif mutation == "witness":
                changed["counterexamples"] = []
            elif mutation == "approval":
                changed["approval"] = "granted"
            elif mutation == "winner":
                changed["best_candidate"]["check"]["formula"] = "false"
            else:
                changed["rounds"].reverse()
            with self.subTest(mutation=mutation):
                self.assertEqual(replay_session(self.project, changed, "test-source")["status"], "fail")
                with self.assertRaisesRegex(ValueError, "replay failed"):
                    evolve_session(self.project, "test-source", previous=changed, max_evaluations=1)

    def test_source_and_project_changes_require_a_new_session(self):
        changed = read_json(PROJECT)
        changed["requirements"][0]["english"] += " Updated intent."
        for project, source in ((self.project, "new-source"), (load_project(changed), "test-source")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                evolve_session(project, source, previous=self.first)

    def test_later_exhaustion_cannot_erase_verified_earlier_winner(self):
        result = evolve_session(self.project, "test-source", previous=self.second, max_evaluations=1)
        self.assertEqual(result["rounds"][-1]["report"]["status"], "no_candidate_found")
        self.assertEqual(result["status"], "candidate_found")
        self.assertEqual(result["target_round"], 2)
        self.assertEqual(result["best_candidate"], self.second["best_candidate"])

    def test_feedback_identifies_global_best_and_retained_history(self):
        result = session_feedback(self.project, self.second, "test-source", max_witnesses=2)
        self.assertEqual(result["session_replay"]["status"], "pass")
        self.assertEqual(result["feedback"]["target_check"]["status"], "pass")
        self.assertEqual(result["target_round"], 2)
        self.assertEqual(len(result["session_archive"]), 2)
        self.assertEqual(result["session_archive_count"], len(self.second["counterexamples"]))
        self.assertGreater(result["session_archive_omitted"], 0)

    def test_invalid_warm_starts_are_rejected_and_never_trusted(self):
        for warm in (False, {}, ["unknown"], ["true"] * 33):
            with self.subTest(warm=warm), self.assertRaises(ValueError):
                evolve(self.project, warm_start=warm)
        result = evolve(self.project, generations=0, warm_start=["false"])
        self.assertEqual(result["status"], "no_candidate_found")
        retained = next(c for c in result["candidates"] if c["origin"] == "retained_candidate")
        self.assertEqual(retained["check"]["status"], "fail")

    def test_session_bounds_are_enforced_before_more_rounds(self):
        session = None
        for _ in range(16):
            session = evolve_session(self.project, "test-source", previous=session, max_evaluations=1)
        with self.assertRaisesRegex(ValueError, "16 rounds"):
            evolve_session(self.project, "test-source", previous=session, max_evaluations=1)
        big = evolve_session(self.project, "test-source", generations=0, max_evaluations=4096)
        big = evolve_session(self.project, "test-source", previous=big, generations=0, max_evaluations=4096)
        with self.assertRaisesRegex(ValueError, "8192"):
            evolve_session(self.project, "test-source", previous=big, max_evaluations=1)

    def test_visual_review_exposes_the_two_changed_input_cases(self):
        review = review_session(self.project, self.second, "test-source")
        changed = [row for row in review["decision_rows"] if row["changed"]]
        self.assertEqual([row["inputs"] for row in changed], [
            {"holding": True, "profit": False, "exit": True},
            {"holding": True, "profit": True, "exit": False}])
        for row in changed:
            self.assertEqual(row["before"], [{"sell": False, "hold_next": True}])
            self.assertEqual(row["after"], [{"sell": True, "hold_next": False}])
        self.assertEqual(review["rows_omitted"], 0)
        self.assertEqual(len(review["behavior_diff"]["newly_permitted"]), 2)
        self.assertEqual(len(review["behavior_diff"]["newly_forbidden"]), 2)

    def test_html_escapes_project_text_and_has_no_external_assets(self):
        review = review_session(self.project, self.first, "test-source")
        review["project_name"] = '<em>literal project name</em>'
        html = render_html(review)
        self.assertIn('&lt;em&gt;literal project name&lt;/em&gt;', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('src=', html)
        self.assertIn('Further repair needed', html)
        self.assertIn('Human approval has not been granted', html)

    def test_review_refuses_unverified_evidence(self):
        altered = copy.deepcopy(self.second)
        altered["unique_candidates"] += 1
        with self.assertRaisesRegex(ValueError, "replay failed"):
            review_session(self.project, altered, "test-source")

    def test_cli_session_to_html_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second, feedback, review, replay = (Path(directory, n) for n in
                ("first.json", "second.json", "feedback.json", "review.html", "replay.json"))
            self.assertEqual(main(["session-evolve", str(PROJECT), "--seed", "0", "--max-evaluations", "64", "--out", str(first)]), 1)
            self.assertEqual(main(["session-evolve", str(PROJECT), "--previous", str(first), "--seed", "1", "--max-evaluations", "128", "--out", str(second)]), 0)
            self.assertEqual(main(["agent-request", str(PROJECT), "--session", str(second), "--out", str(feedback)]), 0)
            self.assertEqual(main(["review", str(PROJECT), str(second), "--out", str(review)]), 0)
            self.assertTrue(review.read_text().startswith('<!doctype html>'))
            self.assertEqual(main(["session-replay", str(PROJECT), str(second), "--out", str(replay)]), 0)
            self.assertEqual(read_json(replay)["rounds_replayed"], 2)


if __name__ == "__main__":
    unittest.main()
