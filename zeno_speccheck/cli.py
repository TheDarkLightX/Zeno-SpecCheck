"""Small imperative shell: files, command arguments, and isolated Tau workers."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import __version__
from .checking import check, semantic_diff
from .evolution import evolve
from .feedback import replay_boolean, verified_feedback
from .logic import parse
from .model import digest, load_project, read_json
from .review import render_html, review_session
from .session import evolve_session, replay_session, session_feedback
from .tau import TauConfig, assemble, check_tau, export_tau, load_tau_project
from .tau_evolution import evolve_tau


REPORT_MAX_BYTES = 64_000_000


def source_digest() -> str:
    hasher = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        hasher.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
    return hasher.hexdigest()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Review and evolve specifications against fixed requirements.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("check", "evolve", "diff", "agent-request", "export-tau", "tau-check", "tau-evolve", "replay",
                 "session-evolve", "session-replay", "review"):
        cmd = commands.add_parser(name)
        cmd.add_argument("project")
        cmd.add_argument("--out", help="write the report to a file instead of stdout")
        if name in ("check", "export-tau"):
            cmd.add_argument("--formula", help="candidate formula; defaults to project seed")
        if name == "diff":
            cmd.add_argument("--old", required=True)
            cmd.add_argument("--new", required=True)
        if name in ("evolve", "tau-evolve", "session-evolve"):
            cmd.add_argument("--seed", type=int, default=0)
            cmd.add_argument("--generations", type=int, default=4 if name == "tau-evolve" else 8)
            cmd.add_argument("--population", type=int, default=4 if name == "tau-evolve" else 8)
            cmd.add_argument("--max-evaluations", type=int, default=16 if name == "tau-evolve" else 256)
            cmd.add_argument("--proposals")
        if name == "session-evolve":
            cmd.add_argument("--previous", help="verified session to extend by one round")
        if name in ("session-replay", "review"):
            cmd.add_argument("session")
        if name == "review":
            cmd.add_argument("--format", choices=("json", "html"), default="html")
        if name in ("tau-check", "tau-evolve"):
            cmd.add_argument("--tau-python", default=sys.executable)
            cmd.add_argument("--tau-module-dir")
            cmd.add_argument("--tau-source-revision")
            cmd.add_argument("--timeout", type=float, default=10)
        if name in ("export-tau", "tau-check"):
            cmd.add_argument("--algebra", choices=("bv[1]", "sbf"), default="bv[1]")
        if name == "tau-check":
            cmd.add_argument("--formula", help="override seed using this project's formula language")
        if name == "replay":
            cmd.add_argument("report")
        if name == "agent-request":
            feedback = cmd.add_mutually_exclusive_group()
            feedback.add_argument("--report", help="verified Boolean evolution report from the previous round")
            feedback.add_argument("--session", help="verified multi-round Boolean session")
            cmd.add_argument("--max-witnesses", type=int, default=32)
    return root


def execute(args) -> dict:
    raw = read_json(args.project)
    is_tau = isinstance(raw, dict) and raw.get("schema") == "zeno/tau-project/v1"
    project = load_tau_project(raw) if is_tau else load_project(raw)
    identity = digest(project) if is_tau else project.identity
    if args.command == "agent-request":
        baseline = None if is_tau else check(project, project.seed)
        request = {"schema": "zeno/agent-request/v1", "project_digest": identity, "project": raw,
                "baseline_check": baseline,
                "response_schema": "zeno/tau-proposals/v1" if is_tau else "zeno/proposals/v1",
                "instructions": ["Return JSON with schema, project_digest, proposals.",
                                 "Each proposal contains only formula and rationale.",
                                 "Propose behavior changes that satisfy the frozen requirements.",
                                 "Do not change assumptions, requirements, variable scope, or approval status.",
                                 "Every proposal will be evaluated; your rationale is not evidence."]}
        if args.report:
            if is_tau:
                raise ValueError("verified report feedback currently requires a Boolean project")
            request["feedback"] = verified_feedback(
                project, read_json(args.report, max_bytes=REPORT_MAX_BYTES), source_digest(),
                max_witnesses=args.max_witnesses)
        if args.session:
            if is_tau:
                raise ValueError("session feedback currently requires a Boolean project")
            request["session_feedback"] = session_feedback(
                project, read_json(args.session, max_bytes=REPORT_MAX_BYTES), source_digest(),
                max_witnesses=args.max_witnesses)
        return request
    if args.command in ("tau-check", "tau-evolve"):
        config = TauConfig(args.tau_python, args.tau_module_dir, args.timeout, args.tau_source_revision)
        if args.command == "tau-evolve":
            if not is_tau:
                raise ValueError("tau-evolve requires a zeno/tau-project/v1 project")
            return evolve_tau(project, config, seed=args.seed, generations=args.generations,
                              population=args.population, max_evaluations=args.max_evaluations,
                              proposal_data=read_json(args.proposals) if args.proposals else None)
        if is_tau:
            result = check_tau(args.formula or assemble(project, tuple(project["seed"])),
                               project["requirements"], config)
        else:
            candidate = parse(args.formula, project.variables) if args.formula else project.seed
            exported = export_tau(project, candidate, args.algebra)
            result = check_tau(exported["formula"], exported["requirements"], config)
            reference = check(project, candidate)
            result["reference_check"] = reference
            result["translation"] = exported
            # The finite domain can catch obligations intentionally outside the Tau export.
            if result["status"] == "pass" and reference["status"] != "pass":
                result["status"] = "fail"
        result["project_digest"] = identity
        return result
    if is_tau:
        raise ValueError("use tau-check, tau-evolve, or agent-request for raw Tau projects")
    if args.command == "check":
        return check(project, parse(args.formula, project.variables) if args.formula else project.seed)
    if args.command == "diff":
        return semantic_diff(project, parse(args.old, project.variables), parse(args.new, project.variables))
    if args.command == "export-tau":
        return export_tau(project, parse(args.formula, project.variables) if args.formula else project.seed, args.algebra)
    if args.command == "evolve":
        return evolve(project, seed=args.seed, generations=args.generations, population=args.population,
                      max_evaluations=args.max_evaluations,
                      proposal_data=read_json(args.proposals) if args.proposals else None)
    if args.command == "session-evolve":
        return evolve_session(project, source_digest(),
                              previous=read_json(args.previous, max_bytes=REPORT_MAX_BYTES) if args.previous else None,
                              seed=args.seed, generations=args.generations, population=args.population,
                              max_evaluations=args.max_evaluations,
                              proposal_data=read_json(args.proposals) if args.proposals else None)
    if args.command in ("session-replay", "review"):
        session = read_json(args.session, max_bytes=REPORT_MAX_BYTES)
        operation = replay_session if args.command == "session-replay" else review_session
        return operation(project, session, source_digest())
    return replay_boolean(project, read_json(args.report, max_bytes=REPORT_MAX_BYTES), source_digest())


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        result["tool"] = {"name": "zeno-speccheck", "version": __version__, "source_digest": source_digest()}
        output = (render_html(result) if args.command == "review" and args.format == "html"
                  else json.dumps(result, indent=2, sort_keys=True) + "\n")
        if len(output.encode("utf-8")) > REPORT_MAX_BYTES:
            raise ValueError("output exceeds the 64 MB report limit; reduce the search budget")
        if args.out:
            destination = Path(args.out)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        status = result.get("status")
        if status in ("fail", "no_candidate_found"):
            return 1
        if status in ("unknown", "backend_error", "invalid", "inconclusive"):
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
