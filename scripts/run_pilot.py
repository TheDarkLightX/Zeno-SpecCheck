"""Produce a compact replayable pilot receipt; full searches remain reproducible."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zeno_speccheck.cli import source_digest
from zeno_speccheck.evolution import evolve
from zeno_speccheck.model import digest, load_project, read_json
from zeno_speccheck.tau import PINNED_TAU, TauConfig, check_tau
from zeno_speccheck.tau_evolution import evolve_tau


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tau-python")
    parser.add_argument("--tau-module-dir")
    parser.add_argument("--tau-source-revision")
    parser.add_argument("--artifact-revision")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    receipt = {"schema": "zeno/pilot/v1", "source_digest": source_digest(),
               "artifact_revision": args.artifact_revision, "boolean_runs": [],
               "scope": "Two illustrative finite repairs and optional small native Tau experiment"}
    for filename, budget in (("authorization.json", 64), ("deflationary_exit.json", 256),
                             ("deflationary_exit.json", 512)):
        project = load_project(read_json(ROOT / "examples" / filename))
        report = evolve(project, max_evaluations=budget)
        winner = report["best_candidate"]
        receipt["boolean_runs"].append({
            "project": f"examples/{filename}", "project_digest": project.identity,
            "seed": 0, "max_evaluations": budget, "status": report["status"],
            "evaluated": report["evaluated_candidates"],
            "counterexamples": len(report["counterexamples"]), "report_digest": digest(report),
            "winner": winner["check"]["formula"] if winner else None,
            "winner_check": winner["check"] if winner else None,
        })
    if args.tau_python:
        config = TauConfig(args.tau_python, args.tau_module_dir, 15, args.tau_source_revision)
        project = read_json(ROOT / "examples/tau_authorization.json")
        report = evolve_tau(project, config)
        receipt["tau_run"] = report
        receipt["full_ltl_probe"] = check_tau("(o1[t]:sbf = 0) U (o1[t]:sbf = 1)", [], config)
    else:
        receipt["tau_run"] = {"status": "not_run", "reason": "no external runtime supplied"}
    receipt["source_manifest"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("zeno_speccheck", "tests", "examples", "scripts")
        for path in sorted((ROOT / folder).rglob("*"))
        if path.is_file() and path.suffix in (".py", ".json") and "__pycache__" not in path.parts
    }
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"out": args.out, "boolean": [r["status"] for r in receipt["boolean_runs"]],
                      "tau": receipt["tau_run"]["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
