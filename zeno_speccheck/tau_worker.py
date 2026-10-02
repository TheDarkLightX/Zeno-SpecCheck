"""One optional native Tau process per request; JSON in, explicit verdicts out."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import sys


def main() -> int:
    request = json.load(sys.stdin)
    result_path = Path(sys.argv[1])
    result = {"schema": "zeno/tau-worker-result/v1", "status": "backend_error", "queries": []}
    try:
        # Native output is bounded separately from the small structured result.
        if os.name == "posix":
            import resource
            resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
        if request.get("module_dir"):
            sys.path.insert(0, request["module_dir"])
        tau = importlib.import_module("tau")
        required = ("valid", "realizable", "reset")
        if any(not callable(getattr(tau, name, None)) for name in required):
            raise RuntimeError("incompatible Tau binding: requires structured valid/realizable/reset API")
        module_path = Path(tau.__file__)
        result["runtime"] = {"module_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
                             "module_name": module_path.name,
                             "declared_source_revision": request.get("source_revision"),
                             "revision_attestation": "caller_declared; module bytes hashed"}
        for query in request["queries"]:
            if query["operation"] not in ("valid", "realizable"):
                raise ValueError("unsupported Tau operation")
            tau.reset()
            if hasattr(tau, "set_ltl_timeout_sec"):
                tau.set_ltl_timeout_sec(max(1, int(request["timeout"])))
            response = getattr(tau, query["operation"])(query["formula"])
            if not hasattr(response, "value") or not hasattr(response, "report"):
                raise RuntimeError("incompatible Tau binding: result lacks value/report")
            value = response.value
            if value is not None and type(value) is not bool:
                raise RuntimeError("non-Boolean decision result")
            errors = getattr(response.report, "errors", [])
            has_error = bool(getattr(response.report, "has_error", False) or errors)
            if has_error:
                value = None
            result["queries"].append({"id": query["id"], "operation": query["operation"],
                                      "formula": query["formula"], "value": value,
                                      "has_error": has_error,
                                      "code_names": list(getattr(response.report, "code_names", [])),
                                      "report": str(response.report)[:16000],
                                      "errors": str(errors)[:16000]})
        result["status"] = "completed"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"[:16000]
    result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    return 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
