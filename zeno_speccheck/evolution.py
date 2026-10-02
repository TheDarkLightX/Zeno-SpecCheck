"""Seeded typed mutation, crossover, semantic deduplication and witness retention."""

import random

from .checking import check, semantic_diff
from .logic import Expr, mutations, parse
from .model import Project, digest, keys


def proposals(project: Project, raw: object | None) -> list[dict]:
    if raw is None:
        return []
    keys(raw, {"schema", "project_digest", "proposals"})
    if raw["schema"] != "zeno/proposals/v1" or raw["project_digest"] != project.identity:
        raise ValueError("proposal schema or frozen project digest does not match")
    if not isinstance(raw["proposals"], list) or len(raw["proposals"]) > 100:
        raise ValueError("at most 100 proposals are supported")
    result = []
    for item in raw["proposals"]:
        keys(item, {"formula", "rationale"})
        if not isinstance(item["rationale"], str) or len(item["rationale"]) > 4096:
            raise ValueError("proposal rationale must be text of at most 4096 characters")
        expr = parse(item["formula"], project.variables)
        if expr.size() > 63:
            raise ValueError("proposal exceeds 63 AST nodes")
        result.append({"formula": str(expr), "rationale": item["rationale"]})
    return result


def evolve(project: Project, *, seed: int = 0, generations: int = 8,
           population: int = 8, max_evaluations: int = 256,
           proposal_data: object | None = None, warm_start: list[str] | None = None) -> dict:
    if not (type(seed) is int and type(generations) is int and 0 <= generations <= 100
            and type(population) is int and 1 <= population <= 32
            and type(max_evaluations) is int and 1 <= max_evaluations <= 4096):
        raise ValueError("invalid search bounds")
    if project.seed.size() > 63:
        raise ValueError("search seed exceeds 63 AST nodes")
    offered = proposals(project, proposal_data)
    if warm_start is not None and (not isinstance(warm_start, list) or len(warm_start) > 32):
        raise ValueError("warm start must contain at most 32 formulas")
    retained = [parse(formula, project.variables) for formula in (warm_start or [])]
    if any(expr.size() > 63 for expr in retained):
        raise ValueError("warm-start candidate exceeds 63 AST nodes")
    rng, records, semantic, seen, archive = random.Random(seed), [], {}, set(), {}
    formula_by_id = {}
    duplicate_count = 0

    def evaluate(expr: Expr, parents: list[str], origin: str, generation: int):
        nonlocal duplicate_count
        spelling = str(expr)
        if spelling in seen or len(records) >= max_evaluations:
            return
        seen.add(spelling)
        try:
            expr = parse(spelling, project.variables)
        except ValueError:
            return
        report = check(project, expr)
        identity = digest({"project": project.identity, "formula": spelling})
        signature = report["semantic_digest"]
        record = {"id": identity, "parents": parents, "origin": origin,
                  "generation": generation, "nodes": expr.size(), "check": report,
                  "equivalent_to": semantic.get(signature)}
        if signature in semantic:
            duplicate_count += 1
        else:
            semantic[signature] = identity
        records.append(record)
        formula_by_id[identity] = expr
        for witness in report["violations"]:
            key = digest(witness)
            if key not in archive:
                archive[key] = {"witness": witness, "first_candidate": identity}

    def rank(record):
        return (len(record["check"]["violations"]), record["nodes"],
                record["check"]["formula"])

    evaluate(project.seed, [], "seed", 0)
    for expr in retained:
        # Retained formulas are checked again; a prior verdict grants no credit.
        evaluate(expr, [], "retained_candidate", 0)
    for item in offered:
        evaluate(parse(item["formula"], project.variables), [], "agent_proposal", 0)
    completed_generations = 0
    for generation in range(1, generations + 1):
        if len(records) >= max_evaluations:
            break
        # Keep the smallest encountered representative of each complete behavior table.
        representatives = {}
        for record in sorted(records, key=rank):
            representatives.setdefault(record["check"]["semantic_digest"], record)
        parents = list(representatives.values())[:population]
        offspring = []
        for parent in parents:
            expr = formula_by_id[parent["id"]]
            offspring.extend((m, [parent["id"]], "typed_mutation")
                             for m in mutations(expr, project.variables))
        for index, left in enumerate(parents):
            for right in parents[index + 1:]:
                for op in ("&&", "||"):
                    child = Expr(op, (formula_by_id[left["id"]], formula_by_id[right["id"]]))
                    if child.size() <= 63:
                        offspring.append((child, [left["id"], right["id"]], "crossover"))
        rng.shuffle(offspring)
        before = len(records)
        # Reserve a useful share of the budget for each generation.
        allowance = max(population, (max_evaluations - before) // (generations - generation + 1))
        for expr, lineage, origin in offspring:
            evaluate(expr, lineage, origin, generation)
            if len(records) - before >= allowance or len(records) >= max_evaluations:
                break
        completed_generations = generation
        if len(records) == before:
            break
    ranked = sorted(records, key=rank)
    passing = [r for r in ranked if r["check"]["status"] == "pass"]
    winner = passing[0] if passing else None
    result = {"schema": "zeno/evolution-report/v1", "project_digest": project.identity,
            "status": "candidate_found" if winner else "no_candidate_found",
            "search": {"seed": seed, "generations": generations, "population": population,
                       "max_evaluations": max_evaluations, "completed_generations": completed_generations,
                       "proposal_digest": digest(offered)},
            "best_candidate": winner, "best_attempt": ranked[0],
            "semantic_diff": semantic_diff(project, project.seed, formula_by_id[winner["id"]]) if winner else None,
            "evaluated_candidates": len(records), "equivalent_candidates": duplicate_count,
            "counterexamples": list(archive.values()), "candidates": records,
            "agent_proposals": offered, "approval": "not_granted",
            "limitations": ["Finite Boolean relations only; no temporal or arithmetic proof.",
                            "Search is incomplete; no candidate found does not establish impossibility.",
                            "Passing means conformance to the frozen requirements, not completeness of intent."]}
    if retained:
        result["warm_start"] = [str(expr) for expr in retained]
    return result
