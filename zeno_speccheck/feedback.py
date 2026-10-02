"""Pure replay and bounded, verified feedback for the next proposal round."""

from .evolution import evolve
from .model import Project, digest, keys


def replay_boolean(project: Project, report: object, source_digest: str) -> dict:
    if (not isinstance(report, dict)
            or report.get("schema") != "zeno/evolution-report/v1"
            or report.get("project_digest") != project.identity):
        raise ValueError("replay requires a matching Boolean evolution report")
    tool = report.get("tool")
    if not isinstance(tool, dict) or tool.get("source_digest") != source_digest:
        raise ValueError("report was produced by different source bytes or lacks provenance")
    search = report.get("search")
    keys(search, {"seed", "generations", "population", "max_evaluations",
                  "completed_generations", "proposal_digest"})
    offered = {"schema": "zeno/proposals/v1", "project_digest": project.identity,
               "proposals": report.get("agent_proposals")}
    replayed = evolve(project, seed=search["seed"], generations=search["generations"],
                      population=search["population"], max_evaluations=search["max_evaluations"],
                      proposal_data=offered, warm_start=report.get("warm_start"))
    original = {k: v for k, v in report.items() if k != "tool"}
    # Canonical JSON equality preserves Boolean versus numeric distinctions.
    return {"schema": "zeno/replay/v1",
            "status": "pass" if digest(replayed) == digest(original) else "fail",
            "project_digest": project.identity, "report_digest": digest(report),
            "comparison": "entire deterministic evolution report"}


def verified_feedback(project: Project, report: object, source_digest: str,
                      *, max_witnesses: int = 32) -> dict:
    if type(max_witnesses) is not int or not 1 <= max_witnesses <= 256:
        raise ValueError("feedback witness limit must be an integer in [1, 256]")
    replay = replay_boolean(project, report, source_digest)
    if replay["status"] != "pass":
        raise ValueError("report replay failed; feedback requires verified evidence")
    target = report["best_candidate"] or report["best_attempt"]
    target_check = target["check"]
    archive = report["counterexamples"]
    # Prioritize current failures, then retain diverse historical obligation
    # witnesses. These remain diagnostic samples; acceptance is still exhaustive.
    remaining = list(target_check["violations"]) + [entry["witness"] for entry in archive]
    selected, seen, covered = [], set(), set()
    for diverse_only in (True, False):
        for witness in remaining:
            identity = digest(witness)
            group = (witness["kind"], witness.get("requirement"), witness.get("example"))
            if identity in seen or (diverse_only and group in covered):
                continue
            if len(selected) >= max_witnesses:
                break
            selected.append(witness)
            seen.add(identity)
            covered.add(group)
    current = {k: v for k, v in target_check.items() if k != "violations"}
    current["violation_count"] = len(target_check["violations"])
    current["violations"] = target_check["violations"][:max_witnesses]
    current["violations_omitted"] = max(0, len(target_check["violations"]) - max_witnesses)
    return {"schema": "zeno/verified-feedback/v1", "replay": replay,
            "search_status": report["status"], "evaluated_candidates": report["evaluated_candidates"],
            "target_candidate_id": target["id"], "target_check": current,
            "counterexamples": selected, "archive_digest": digest(archive),
            "archive_witness_count": len(archive), "witnesses_omitted": len(archive) - len(selected),
            "approval": "not_granted",
            "instructions": [
                "Improve the target candidate against the unchanged project.",
                "Historical witnesses describe failures of earlier candidates; the target may already resolve them.",
                "Feedback may omit witnesses. Every new candidate is checked over the full declared domain.",
                "Passing candidates need no repair; any proposed simplification must pass the same gates."]}
