"""Tau's trace validity and causal realizability remain distinct operations."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import json

from .logic import Expr, tau_formula
from .model import Project, digest, keys


PINNED_TAU = "31b5b3cfa546d1769cb27c882f131a2914452b55"


@dataclass(frozen=True)
class TauConfig:
    python: str = sys.executable
    module_dir: str | None = None
    timeout: float = 10.0
    source_revision: str | None = None

    def __post_init__(self):
        if not 0 < self.timeout <= 300:
            raise ValueError("Tau timeout must be in (0, 300] seconds")
        if self.source_revision is not None and not re.fullmatch(r"[a-f0-9]{40}", self.source_revision):
            raise ValueError("Tau source revision must be a full commit SHA")


def run_queries(queries: list[dict], config: TauConfig) -> dict:
    request = {"queries": queries, "module_dir": config.module_dir,
               "timeout": config.timeout, "source_revision": config.source_revision}
    with tempfile.TemporaryDirectory(prefix="zeno-tau-") as temporary:
        destination = Path(temporary) / "result.json"
        environment = os.environ.copy()
        package_root = str(Path(__file__).resolve().parent.parent)
        environment["PYTHONPATH"] = package_root
        with tempfile.TemporaryFile() as log:
            try:
                process = subprocess.Popen(
                    [config.python, "-m", "zeno_speccheck.tau_worker", str(destination)],
                    stdin=subprocess.PIPE, stdout=log, stderr=log, env=environment,
                    start_new_session=(os.name == "posix"), text=True,
                )
            except OSError as error:
                return {"status": "backend_error", "error": str(error), "queries": []}
            try:
                process.communicate(json.dumps(request), timeout=config.timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.communicate()
                return {"status": "unknown", "reason": "worker_timeout", "queries": [],
                        "requested_queries": queries, "timeout_seconds": config.timeout}
            log.seek(0)
            diagnostic = log.read(32000).decode("utf-8", errors="replace")
            if not destination.exists():
                return {"status": "backend_error", "error": "worker exited without a result",
                        "returncode": process.returncode, "log": diagnostic, "queries": []}
            try:
                result = json.loads(destination.read_text(encoding="utf-8"))
            except (ValueError, OSError) as error:
                return {"status": "backend_error", "error": str(error), "queries": []}
            result["log"] = diagnostic
            result["timeout_seconds"] = config.timeout
            result["returncode"] = process.returncode
            return result


def formula_text(text: str) -> str:
    """An entire Tau formula, never REPL commands, definitions or file directives."""
    if not isinstance(text, str) or not text.strip() or len(text) > 32000:
        raise ValueError("Tau formula must be nonempty text of at most 32000 characters")
    text = text.strip()
    if text.endswith("."):
        text = text[:-1].rstrip()
    if not text or any(token in text for token in (".", ";", "\x00", '"', "#", "//", "/*")):
        raise ValueError("Tau profile accepts one formula, without declarations, quoted strings, or comments")
    stack = []
    closing = {")": "(", "]": "[", "}": "{"}
    for char in text:
        if char in "([{":
            stack.append(char)
        elif char in closing:
            if not stack or stack.pop() != closing[char]:
                raise ValueError("unbalanced Tau formula delimiters")
    if stack:
        raise ValueError("unbalanced Tau formula delimiters")
    return text


def check_tau(candidate: str, requirements: list[dict], config: TauConfig) -> dict:
    candidate = formula_text(candidate)
    queries = [{"id": "$realizability", "operation": "realizable", "formula": candidate + "."}]
    for item in requirements:
        goal = formula_text(item["formula"])
        queries.append({"id": item["id"], "operation": "valid",
                        "formula": f"({candidate}) -> ({goal})."})
    result = run_queries(queries, config)
    if result["status"] == "completed":
        values = [query["value"] for query in result["queries"]]
        complete = len(values) == len(queries) and result.get("returncode") == 0
        clean = all(not q.get("has_error", False) for q in result["queries"])
        status = "fail" if any(v is False for v in values) else (
            "pass" if complete and clean and values and all(v is True for v in values) else "unknown")
    else:
        status = result["status"]
    return {"status": status, "formula": candidate, "backend": result,
            "evidence_kind": "tau_solver_reported", "approval": "not_granted",
            "semantics": "causal realizability plus universal trace implication",
            "counterexample_extraction": "not_available_in_this_adapter"}


def export_tau(project: Project, candidate: Expr, algebra: str = "bv[1]") -> dict:
    streams = {name: f"i{index + 1}" for index, name in enumerate(project.inputs)}
    streams.update({name: f"o{index + 1}" for index, name in enumerate(project.outputs)})
    def domain(names):
        if algebra == "bv[1]":
            return "T"
        return " && ".join(f"({streams[name]}[t]:sbf = 0:sbf || {streams[name]}[t]:sbf = 1:sbf)"
                           for name in names) or "T"
    assumptions = f"({domain(project.inputs)} && {tau_formula(project.assumption, streams, algebra)})"
    outputs = domain(project.outputs)
    def temporal(expr):
        return f"always ({assumptions} -> ({outputs} && {tau_formula(expr, streams, algebra)}))"
    return {"formula": temporal(candidate), "project_digest": project.identity,
            "algebra": algebra, "streams": streams,
            "requirements": [{"id": r.id, "english": r.english, "formula": temporal(r.formula)}
                             for r in project.requirements],
            "limitations": ["Stateless relation translation only; no state recurrence or liveness inferred.",
                            "Finite examples and deterministic-output requirements remain checked by the reference checker."]}


def load_tau_project(raw: object) -> dict:
    keys(raw, {"schema", "name", "requirements", "clauses", "seed"})
    if raw["schema"] != "zeno/tau-project/v1" or not isinstance(raw["name"], str):
        raise ValueError("unsupported Tau project schema or name")
    if not isinstance(raw["requirements"], list) or not isinstance(raw["clauses"], list):
        raise ValueError("Tau requirements and clauses must be lists")
    if not 1 <= len(raw["clauses"]) <= 16 or len(raw["requirements"]) > 32:
        raise ValueError("support 1..16 clause slots and at most 32 requirements")
    ids = set()
    for item in raw["requirements"]:
        keys(item, {"id", "english", "formula"})
    for item in raw["clauses"]:
        keys(item, {"id", "variants"})
    for item in raw["requirements"] + raw["clauses"]:
        if not isinstance(item["id"], str) or not item["id"] or item["id"].startswith("$") or item["id"] in ids:
            raise ValueError("IDs must be unique, nonempty and not reserved")
        ids.add(item["id"])
        if "formula" in item:
            if not isinstance(item["english"], str):
                raise ValueError("English requirement must be text")
            formula_text(item["formula"])
        else:
            if not isinstance(item["variants"], list) or not 1 <= len(item["variants"]) <= 32:
                raise ValueError("each clause requires 1..32 variants")
            for variant in item["variants"]:
                formula_text(variant)
    if not isinstance(raw["seed"], list) or len(raw["seed"]) != len(raw["clauses"]):
        raise ValueError("seed must choose one variant per clause slot")
    for index, slot in zip(raw["seed"], raw["clauses"]):
        if type(index) is not int or not 0 <= index < len(slot["variants"]):
            raise ValueError("invalid seed variant")
    return json.loads(json.dumps(raw))


def assemble(project: dict, genome: tuple[int, ...]) -> str:
    return " && ".join(f"({formula_text(slot['variants'][index])})"
                       for slot, index in zip(project["clauses"], genome))
