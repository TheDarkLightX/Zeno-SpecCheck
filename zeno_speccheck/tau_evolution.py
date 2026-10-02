"""Evolution over whole Tau clause alternatives, preserving their source context."""

import random

from .model import digest, keys
from .tau import TauConfig, assemble, check_tau, formula_text, load_tau_project


def tau_proposals(project: dict, raw: object | None) -> list[dict]:
    if raw is None:
        return []
    keys(raw, {"schema", "project_digest", "proposals"})
    if raw["schema"] != "zeno/tau-proposals/v1" or raw["project_digest"] != digest(project):
        raise ValueError("Tau proposals must bind the unchanged project digest")
    if not isinstance(raw["proposals"], list) or len(raw["proposals"]) > 32:
        raise ValueError("support at most 32 Tau proposals")
    result = []
    for item in raw["proposals"]:
        keys(item, {"formula", "rationale"})
        if not isinstance(item["rationale"], str) or len(item["rationale"]) > 4096:
            raise ValueError("proposal rationale must be bounded text")
        result.append({"formula": formula_text(item["formula"]), "rationale": item["rationale"]})
    return result


def evolve_tau(raw: dict, config: TauConfig, *, seed: int = 0, generations: int = 4,
               population: int = 4, max_evaluations: int = 16,
               proposal_data: object | None = None) -> dict:
    project = load_tau_project(raw)
    if not (type(seed) is int and type(generations) is int and 0 <= generations <= 100
            and type(population) is int and 1 <= population <= 16
            and type(max_evaluations) is int and 1 <= max_evaluations <= 256):
        raise ValueError("invalid Tau search bounds")
    offered = tau_proposals(project, proposal_data)
    rng, records, seen, genomes = random.Random(seed), [], set(), {}
    identity = digest(project)

    def evaluate(formula, parent_ids, origin, generation, genome=None):
        if formula in seen or len(records) >= max_evaluations:
            return
        seen.add(formula)
        result = check_tau(formula, project["requirements"], config)
        record = {"id": digest({"project": identity, "formula": formula}),
                  "parents": parent_ids, "origin": origin, "generation": generation,
                  "genome": list(genome) if genome is not None else None, "check": result}
        records.append(record)
        if genome is not None:
            genomes[record["id"]] = genome

    def rank(record):
        result = record["check"]
        values = [q["value"] for q in result["backend"].get("queries", [])]
        undecided = result["status"] in ("unknown", "backend_error", "invalid")
        return (result["status"] != "pass", undecided, sum(v is False for v in values),
                len(result["formula"]), result["formula"])

    initial = tuple(project["seed"])
    evaluate(assemble(project, initial), [], "seed", 0, initial)
    # A missing/incompatible engine cannot usefully evaluate a population.
    if records[0]["check"]["status"] != "backend_error":
        for item in offered:
            evaluate(item["formula"], [], "agent_proposal", 0)
        for generation in range(1, generations + 1):
            if len(records) >= max_evaluations:
                break
            parents = [r for r in sorted(records, key=rank) if r["id"] in genomes][:population]
            offspring = []
            for parent in parents:
                genome = genomes[parent["id"]]
                for index, slot in enumerate(project["clauses"]):
                    for allele in range(len(slot["variants"])):
                        child = list(genome)
                        child[index] = allele
                        offspring.append((tuple(child), [parent["id"]], "clause_mutation"))
            for index, left in enumerate(parents):
                for right in parents[index + 1:]:
                    a, b = genomes[left["id"]], genomes[right["id"]]
                    child = tuple(rng.choice(pair) for pair in zip(a, b))
                    offspring.append((child, [left["id"], right["id"]], "clause_crossover"))
            rng.shuffle(offspring)
            before = len(records)
            for genome, parents_ids, origin in offspring:
                evaluate(assemble(project, genome), parents_ids, origin, generation, genome)
                if len(records) >= max_evaluations:
                    break
            if before == len(records):
                break
    passing = [r for r in sorted(records, key=rank) if r["check"]["status"] == "pass"]
    unresolved = any(r["check"]["status"] in ("unknown", "backend_error", "invalid") for r in records)
    return {"schema": "zeno/tau-evolution-report/v1", "project_digest": identity,
            "status": "candidate_found" if passing else ("inconclusive" if unresolved else "no_candidate_found"),
            "search": {"seed": seed, "generations": generations, "population": population,
                       "max_evaluations": max_evaluations, "proposal_digest": digest(offered)},
            "best_candidate": passing[0] if passing else None, "candidates": records,
            "evaluated_candidates": len(records), "agent_proposals": offered,
            "approval": "not_granted", "limitations": [
                "Native solver verdicts are not independently checked proof certificates.",
                "Raw Tau search deduplicates source, not arbitrary temporal semantic equivalence.",
                "No general temporal witness extraction; failed requirements remain verdicts with diagnostics.",
                "An agent proposal supplies a whole formula; symbolic search mutates configured clause variants."]}
