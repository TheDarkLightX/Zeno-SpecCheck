"""Pure, replayable multi-round evolution with retained candidates and witnesses."""

from .evolution import evolve
from .feedback import verified_feedback
from .model import Project, digest, keys


MAX_ROUNDS = 16
MAX_SESSION_EVALUATIONS = 8192


def candidate_rank(record: dict) -> tuple:
    return (len(record["check"]["violations"]), record["nodes"], record["check"]["formula"])


def retain(rounds: list[dict], population: int) -> list[str]:
    representatives = {}
    candidates = (candidate for entry in rounds for candidate in entry["report"]["candidates"])
    for record in sorted(candidates, key=candidate_rank):
        representatives.setdefault(record["check"]["semantic_digest"], record["check"]["formula"])
    return list(representatives.values())[:population]


def _assemble(project: Project, source_digest: str, rounds: list[dict]) -> dict:
    archive, unique = {}, set()
    best, best_round = None, None
    for entry in rounds:
        report = entry["report"]
        for candidate in report["candidates"]:
            unique.add(candidate["id"])
            if best is None or candidate_rank(candidate) < candidate_rank(best):
                best, best_round = candidate, entry["number"]
        for item in report["counterexamples"]:
            archive.setdefault(digest(item["witness"]), item | {"first_round": entry["number"]})
    accepted = best["check"]["status"] == "pass"
    return {"schema": "zeno/session/v1", "project_digest": project.identity,
            "source_digest": source_digest, "rounds": rounds,
            "status": "candidate_found" if accepted else "no_candidate_found",
            "best_candidate": best if accepted else None, "best_attempt": best,
            "target_round": best_round, "counterexamples": list(archive.values()),
            "evaluated_candidates": sum(r["report"]["evaluated_candidates"] for r in rounds),
            "unique_candidates": len(unique), "approval": "not_granted",
            "limitations": ["Finite Boolean relations only; no temporal or arithmetic proof.",
                            "Rounds retain diverse candidates, not the random generator state.",
                            "Retained candidates are rechecked and consume the new round's budget.",
                            "Failed search is not a proof of impossibility."]}


def _append(project: Project, source_digest: str, rounds: list[dict], **options) -> dict:
    if len(rounds) >= MAX_ROUNDS:
        raise ValueError(f"session is limited to {MAX_ROUNDS} rounds")
    budget = options.get("max_evaluations", 256)
    previous_budget = sum(r["report"]["search"]["max_evaluations"] for r in rounds)
    if type(budget) is not int or budget + previous_budget > MAX_SESSION_EVALUATIONS:
        raise ValueError(f"session total requested budget exceeds {MAX_SESSION_EVALUATIONS}")
    population = options.get("population", 8)
    if type(population) is not int or not 1 <= population <= 32:
        raise ValueError("session population must be an integer in [1, 32]")
    report = evolve(project, warm_start=retain(rounds, population), **options)
    entry = {"number": len(rounds) + 1,
             "previous_round_digest": digest(rounds[-1]) if rounds else None, "report": report}
    return _assemble(project, source_digest, rounds + [entry])


def replay_session(project: Project, session: object, source_digest: str) -> dict:
    keys(session, {"schema", "project_digest", "source_digest", "rounds", "status",
                   "best_candidate", "best_attempt", "target_round", "counterexamples",
                   "evaluated_candidates", "unique_candidates", "approval", "limitations"}, {"tool"})
    if session["schema"] != "zeno/session/v1" or session["project_digest"] != project.identity:
        raise ValueError("session requires the unchanged Boolean project")
    if session["source_digest"] != source_digest:
        raise ValueError("session was produced by different source bytes")
    rounds = session["rounds"]
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= MAX_ROUNDS:
        raise ValueError(f"session must contain 1..{MAX_ROUNDS} rounds")
    regenerated = None
    for number, entry in enumerate(rounds, 1):
        keys(entry, {"number", "previous_round_digest", "report"})
        report = entry["report"]
        if not isinstance(report, dict):
            raise ValueError("session round report must be an object")
        search = report.get("search")
        keys(search, {"seed", "generations", "population", "max_evaluations",
                      "completed_generations", "proposal_digest"})
        offered = {"schema": "zeno/proposals/v1", "project_digest": project.identity,
                   "proposals": report.get("agent_proposals")}
        regenerated = _append(project, source_digest, regenerated["rounds"] if regenerated else [],
                              seed=search["seed"], generations=search["generations"],
                              population=search["population"], max_evaluations=search["max_evaluations"],
                              proposal_data=offered)
        if digest(regenerated["rounds"][-1]) != digest(entry):
            return {"status": "fail", "mismatching_round": number, "session_digest": digest(session)}
    original = {k: v for k, v in session.items() if k != "tool"}
    return {"schema": "zeno/session-replay/v1", "project_digest": project.identity,
            "session_digest": digest(session), "rounds_replayed": len(rounds),
            "status": "pass" if digest(regenerated) == digest(original) else "fail",
            "comparison": "all rounds, retention, lineage, cumulative witnesses, and final selection"}


def require_session(project: Project, session: object, source_digest: str) -> dict:
    result = replay_session(project, session, source_digest)
    if result["status"] != "pass":
        raise ValueError("session replay failed; continuation requires verified evidence")
    return result


def evolve_session(project: Project, source_digest: str, *, previous: object | None = None,
                   **options) -> dict:
    if previous is not None:
        require_session(project, previous, source_digest)
    return _append(project, source_digest, previous["rounds"] if previous else [], **options)


def session_feedback(project: Project, session: object, source_digest: str,
                     *, max_witnesses: int = 32) -> dict:
    replay = require_session(project, session, source_digest)
    # Use the round containing the global best. Reuse the single-report feedback
    # boundary; only rechecked, reproducible evidence reaches the next proposer.
    target = session["rounds"][session["target_round"] - 1]["report"]
    feedback = verified_feedback(project, target | {"tool": {"source_digest": source_digest}},
                                 source_digest, max_witnesses=max_witnesses)
    history = session["counterexamples"]
    return {"schema": "zeno/session-feedback/v1", "session_replay": replay,
            "target_round": session["target_round"], "feedback": feedback,
            "session_archive": history[:max_witnesses], "session_archive_digest": digest(history),
            "session_archive_count": len(history), "session_archive_omitted": max(0, len(history) - max_witnesses),
            "approval": "not_granted"}
