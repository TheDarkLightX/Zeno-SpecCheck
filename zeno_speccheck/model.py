"""Validated immutable project inputs and content identities."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .logic import Expr, parse


def digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(data.encode()).hexdigest()


def strict_json(source: str) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(source, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def read_json(path: str | Path, *, max_bytes: int = 1_000_000) -> object:
    # Reports can be much larger than project/proposal inputs. Bound the read
    # itself so an oversized file is rejected before loading all of its bytes.
    with Path(path).open("rb") as source:
        data = source.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"input exceeds {max_bytes} bytes")
    return strict_json(data.decode("utf-8"))


def keys(value: object, required: set[str], optional: set[str] = frozenset()) -> None:
    if not isinstance(value, dict) or set(value) - required - optional or required - set(value):
        raise ValueError(f"expected keys {sorted(required)}, optional {sorted(optional)}")


@dataclass(frozen=True)
class Requirement:
    id: str
    english: str
    formula: Expr


@dataclass(frozen=True)
class Example:
    id: str
    values: tuple[tuple[str, bool], ...]
    allowed: bool


@dataclass(frozen=True)
class Project:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    assumption: Expr
    requirements: tuple[Requirement, ...]
    examples: tuple[Example, ...]
    seed: Expr
    deterministic: bool
    identity: str

    @property
    def variables(self) -> tuple[str, ...]:
        return self.inputs + self.outputs


def load_project(raw: object) -> Project:
    keys(raw, {"schema", "name", "inputs", "outputs", "assumption", "requirements", "seed"},
         {"examples", "deterministic"})
    if raw["schema"] != "zeno/boolean-project/v1":
        raise ValueError("unsupported project schema")
    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise ValueError("project requires a name")
    for field in ("inputs", "outputs"):
        names = raw[field]
        if not isinstance(names, list) or any(
            not isinstance(n, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n)
            or n in ("true", "false") for n in names
        ):
            raise ValueError("variables must be identifier lists")
    variables = tuple(raw["inputs"] + raw["outputs"])
    if not raw["outputs"] or len(variables) > 12 or len(set(variables)) != len(variables):
        raise ValueError("require outputs and at most 12 distinct input/output variables")
    if type(raw.get("deterministic", False)) is not bool:
        raise ValueError("deterministic must be a Boolean")
    requirements, examples, ids = [], [], set()
    if not isinstance(raw["requirements"], list) or not isinstance(raw.get("examples", []), list):
        raise ValueError("requirements and examples must be lists")
    for item in raw["requirements"]:
        keys(item, {"id", "english", "formula"})
        if not isinstance(item["english"], str):
            raise ValueError("requirement english must be text")
        requirements.append(Requirement(item["id"], item["english"], parse(item["formula"], variables)))
    for item in raw.get("examples", []):
        keys(item, {"id", "values", "allowed"})
        if not isinstance(item["values"], dict) or set(item["values"]) != set(variables):
            raise ValueError("examples must assign every declared variable")
        if type(item["allowed"]) is not bool or any(type(x) is not bool for x in item["values"].values()):
            raise ValueError("example values and allowed must be JSON Booleans")
        examples.append(Example(item["id"], tuple(sorted(item["values"].items())), item["allowed"]))
    for item in requirements + examples:
        if not isinstance(item.id, str) or not item.id or item.id in ids:
            raise ValueError("requirement and example IDs must be unique nonempty strings")
        ids.add(item.id)
    project = Project(raw["name"], tuple(raw["inputs"]), tuple(raw["outputs"]),
                      parse(raw["assumption"], tuple(raw["inputs"])), tuple(requirements),
                      tuple(examples), parse(raw["seed"], variables),
                      raw.get("deterministic", False), digest(raw))
    for item in examples:
        values = dict(item.values)
        if not project.assumption.evaluate(values):
            raise ValueError(f"example {item.id} lies outside the fixed input domain")
        if item.allowed and not all(r.formula.evaluate(values) for r in requirements):
            raise ValueError(f"positive example {item.id} contradicts a protected requirement")
    return project
