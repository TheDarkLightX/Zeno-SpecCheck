import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from zeno_speccheck.cli import main
from zeno_speccheck.logic import parse
from zeno_speccheck.model import load_project, read_json
from zeno_speccheck.evolution import evolve


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_evolution_report_replays_and_tampering_is_detected(self):
        project = str(ROOT / "examples/authorization.json")
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.json"
            self.assertEqual(main(["evolve", project, "--out", str(report), "--max-evaluations", "64"]), 0)
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(main(["replay", project, str(report)]), 0)
            self.assertEqual(json.loads(captured.getvalue())["status"], "pass")
            data = json.loads(report.read_text())
            data["best_candidate"]["check"]["formula"] = "false"
            report.write_text(json.dumps(data))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["replay", project, str(report)]), 1)

    def test_exit_policy_repair_finds_a_valid_candidate(self):
        project = load_project(read_json(ROOT / "examples/deflationary_exit.json"))
        result = evolve(project, seed=0, max_evaluations=512)
        self.assertEqual(result["status"], "candidate_found")
        candidate = parse(result["best_candidate"]["check"]["formula"])
        # Independent policy, including the historically troublesome exit/no-profit case.
        from itertools import product
        for holding, profit, exit_signal, sell, next_hold in product([False, True], repeat=5):
            row = dict(holding=holding, profit=profit, exit=exit_signal, sell=sell, hold_next=next_hold)
            expected_sell = holding and (profit or exit_signal)
            expected_hold = holding and not expected_sell
            self.assertEqual(candidate.evaluate(row), sell == expected_sell and next_hold == expected_hold)


if __name__ == "__main__":
    unittest.main()
