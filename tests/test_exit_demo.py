from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from zeno_speccheck.logic import parse
from zeno_speccheck.model import load_project, read_json
from zeno_speccheck.tau import export_tau, formula_text


ROOT = Path(__file__).resolve().parents[1]


class ExitDemoArtifactTests(unittest.TestCase):
    def test_demo_emits_selected_tau_spec_without_a_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/run_exit_demo.py'), '--out', folder],
                capture_output=True, text=True, check=True, timeout=30,
            )
            destination = Path(folder)
            summary = read_json(destination / 'summary.json')
            artifact = summary['tau_artifact']
            tau_path = destination / artifact['path']
            tau_bytes = tau_path.read_bytes()
            project = load_project(read_json(ROOT / 'examples/deflationary_exit.json'))
            expected = export_tau(project, parse(summary['winner']['formula']), 'sbf')
            self.assertEqual(formula_text(tau_bytes.decode('utf-8')), expected['formula'])
            self.assertTrue(tau_bytes.endswith(b'.\n'))
            self.assertEqual(artifact['sha256'], sha256(tau_bytes).hexdigest())
            self.assertEqual(artifact['streams'], expected['streams'])
            self.assertEqual(summary['tau_status'], 'not_run')
            self.assertEqual(json.loads(result.stdout)['tau_spec'], str(tau_path))


if __name__ == '__main__':
    unittest.main()
