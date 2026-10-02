"""Exhaustive relation checking over the explicitly declared Boolean domain."""

from itertools import product

from .logic import Expr
from .model import Project, digest


def assignments(names: tuple[str, ...]):
    for values in product((False, True), repeat=len(names)):
        yield dict(zip(names, values))


def behavior(project: Project, candidate: Expr) -> tuple[bool, ...]:
    return tuple(project.assumption.evaluate(row) and candidate.evaluate(row)
                 for row in assignments(project.variables))


def check(project: Project, candidate: Expr) -> dict:
    if candidate.variables() - set(project.variables):
        raise ValueError("candidate refers to undeclared variables")
    violations, admitted, permitted, ambiguous = [], 0, 0, 0
    for inputs in assignments(project.inputs):
        if not project.assumption.evaluate(inputs):
            continue
        admitted += 1
        outcomes = []
        for outputs in assignments(project.outputs):
            row = inputs | outputs
            if not candidate.evaluate(row):
                continue
            outcomes.append(outputs)
            permitted += 1
            for requirement in project.requirements:
                if not requirement.formula.evaluate(row):
                    violations.append({"kind": "forbidden_behavior", "requirement": requirement.id,
                                       "values": row})
        if not outcomes:
            violations.append({"kind": "dead_end_input", "inputs": inputs})
        if len(outcomes) > 1:
            ambiguous += 1
            if project.deterministic:
                violations.append({"kind": "multiple_outputs", "inputs": inputs,
                                   "outputs": outcomes[:2]})
    if not admitted:
        violations.append({"kind": "empty_input_domain"})
    for example in project.examples:
        row = dict(example.values)
        if candidate.evaluate(row) != example.allowed:
            violations.append({"kind": "example_mismatch", "example": example.id,
                               "values": row, "expected_allowed": example.allowed})
    bits = behavior(project, candidate)
    return {"status": "pass" if not violations else "fail",
            "evidence_kind": "exhaustive_boolean_relation",
            "project_digest": project.identity, "formula": str(candidate),
            "semantic_digest": digest({"project": project.identity, "relation": bits}),
            "scope": {"inputs": list(project.inputs), "outputs": list(project.outputs),
                      "assumption": str(project.assumption), "total_assignments": 2 ** len(project.variables)},
            "admitted_inputs": admitted, "permitted_pairs": permitted,
            "inputs_with_multiple_outputs": ambiguous, "violations": violations,
            "approval": "not_granted"}


def semantic_diff(project: Project, old: Expr, new: Expr) -> dict:
    added, removed = [], []
    for row in assignments(project.variables):
        if not project.assumption.evaluate(row):
            continue
        a, b = old.evaluate(row), new.evaluate(row)
        if b and not a:
            added.append(row)
        if a and not b:
            removed.append(row)
    return {"project_digest": project.identity, "equivalent": not added and not removed,
            "newly_permitted": added, "newly_forbidden": removed,
            "scope": "complete declared Boolean relation under fixed assumptions"}
