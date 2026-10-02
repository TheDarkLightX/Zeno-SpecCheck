"""Pure human review of a verified Boolean evolution session."""

from html import escape
import json

from .checking import assignments, check, semantic_diff
from .logic import parse
from .model import Project, digest
from .session import require_session


def review_session(project: Project, session: object, source_digest: str) -> dict:
    replay = require_session(project, session, source_digest)
    target = session["best_candidate"] or session["best_attempt"]
    candidate = parse(target["check"]["formula"], project.variables)
    rows, omitted = [], 0
    for inputs in assignments(project.inputs):
        if not project.assumption.evaluate(inputs):
            continue
        if len(rows) >= 64:
            omitted += 1
            continue
        before, after, required = [], [], []
        for outputs in assignments(project.outputs):
            row = inputs | outputs
            if project.seed.evaluate(row):
                before.append(outputs)
            if candidate.evaluate(row):
                after.append(outputs)
            if all(r.formula.evaluate(row) for r in project.requirements):
                required.append(outputs)
        rows.append({"inputs": inputs, "before": before, "after": after,
                     "requirement_permitted": required, "changed": before != after})
    progress = []
    for entry in session["rounds"]:
        report = entry["report"]
        best = report["best_candidate"] or report["best_attempt"]
        progress.append({"round": entry["number"], "status": report["status"],
                         "evaluated_candidates": report["evaluated_candidates"],
                         "retained_formulas": len(report.get("warm_start", [])),
                         "agent_proposals": len(report["agent_proposals"]),
                         "remaining_violations": len(best["check"]["violations"]),
                         "formula": best["check"]["formula"], "origin": best["origin"],
                         "candidate_id": best["id"], "parents": best["parents"],
                         "nodes": best["nodes"]})
    return {"schema": "zeno/review/v1", "project_digest": project.identity,
            "session_digest": digest(session), "project_name": project.name,
            "status": "pass" if session["best_candidate"] else "fail", "replay": replay,
            "baseline_check": check(project, project.seed), "target_check": target["check"],
            "requirements": [{"id": r.id, "english": r.english, "formula": str(r.formula)}
                             for r in project.requirements],
            "progress": progress, "decision_rows": rows, "rows_omitted": omitted,
            "behavior_diff": semantic_diff(project, project.seed, candidate),
            "evaluated_candidates": session["evaluated_candidates"],
            "unique_candidates": session["unique_candidates"],
            "retained_witnesses": len(session["counterexamples"]),
            "approval": "not_granted", "scope": "Complete finite Boolean checking; one-step relation only."}


def _code(value: str) -> str:
    return '<code>' + escape(value) + '</code>'


def _values(values: dict) -> str:
    return ', '.join(f'{escape(name)}={int(value)}' for name, value in values.items()) or '(no inputs)'


def _outputs(outcomes: list[dict]) -> str:
    return '<br>'.join(_values(row) for row in outcomes) or '<em>No permitted output</em>'


def render_html(review: dict) -> str:
    """Render inert, escaped evidence; it neither grants approval nor executes proposals."""
    target = review["target_check"]
    status = 'Candidate satisfies configured checks' if target["status"] == 'pass' else 'Further repair needed'
    requirements = ''.join('<li><strong>' + escape(r["id"]) + '</strong> ' + escape(r["english"])
                           + '<br>' + _code(r["formula"]) + '</li>' for r in review["requirements"])
    rounds = ''.join(f'<tr><td>{r["round"]}</td><td>{r["evaluated_candidates"]}</td>'
                     f'<td>{r["retained_formulas"]}</td><td>{r["remaining_violations"]}</td>'
                     f'<td>{r["nodes"]}</td><td>{escape(r["origin"])}</td></tr>' for r in review["progress"])
    formulas = ''.join('<details><summary>Round ' + str(r["round"]) + ' candidate</summary><p>'
                       + _code(r["formula"]) + '</p><p>Candidate: ' + _code(r["candidate_id"])
                       + '</p><p>Parents: ' + _code(', '.join(r["parents"]) or 'None in this round')
                       + '</p></details>' for r in review["progress"])
    decisions = ''.join('<tr' + (' class="changed"' if row["changed"] else '') + '><td>'
                        + _values(row["inputs"]) + '</td><td>' + _outputs(row["before"]) + '</td><td>'
                        + _outputs(row["after"]) + '</td><td>' + _outputs(row["requirement_permitted"])
                        + '</td><td>' + ('Changed' if row["changed"] else 'Unchanged') + '</td></tr>'
                        for row in review["decision_rows"])
    failures = escape(json.dumps(review["baseline_check"]["violations"], indent=2))
    omitted = f'<p>{review["rows_omitted"]} input rows omitted from this view.</p>' if review["rows_omitted"] else ''
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Zeno-SpecCheck · Evolution review</title><style>
:root{color-scheme:light;--ink:#18312c;--muted:#5d7169;--line:#cbd9d1;--accent:#16654a}
*{box-sizing:border-box}body{margin:0;background:#f4f7f2;color:var(--ink);font:16px/1.6 system-ui,sans-serif}
main{max-width:1160px;margin:auto;padding:48px 24px}header{margin-bottom:30px}.eyebrow{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1{font-size:clamp(28px,4vw,44px);line-height:1.15;max-width:900px;margin:14px 0}h2{font-size:23px;margin:0 0 12px}p{margin:8px 0}.muted{color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}.card,section{background:white;border:1px solid var(--line);border-radius:12px;padding:22px}.card strong{font-size:30px;display:block}.card span{font-size:14px;color:var(--muted)}section{margin:20px 0}
code{font:14px/1.7 ui-monospace,monospace;overflow-wrap:anywhere;background:#eef3ee;padding:2px 5px;border-radius:4px}pre{font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:13px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-weight:600;background:#f5f8f4}.scroll{overflow-x:auto}tr.changed td{background:#e8f5ed}li{margin:16px 0}summary{cursor:pointer;color:var(--accent);padding:10px 0;font-weight:600}.pill{display:inline-block;border:1px solid var(--line);border-radius:20px;padding:4px 12px;background:#e8f5ed;font-size:14px}.note{border-left:3px solid #cfb16a;padding-left:14px}footer{font-size:13px;color:var(--muted);overflow-wrap:anywhere}
@media(max-width:640px){main{padding:24px 14px}.cards{grid-template-columns:1fr}.card{padding:14px}section{padding:16px}th,td{padding:10px 8px}}
</style></head><body><main><header><div class="eyebrow">Zeno-SpecCheck / Evolution review</div><h1>''' + escape(review["project_name"]) + '''</h1><p class="pill">''' + status + '''</p>
<p class="muted">Fixed requirements. Retained candidates. Replayed evidence.</p></header>
<div class="cards"><div class="card"><strong>''' + str(review["evaluated_candidates"]) + '''</strong><span>Candidate evaluations across all rounds</span></div>
<div class="card"><strong>''' + str(review["retained_witnesses"]) + '''</strong><span>Distinct diagnostic witnesses retained</span></div>
<div class="card"><strong>''' + str(target["scope"]["total_assignments"]) + '''</strong><span>Boolean assignments in each exhaustive check</span></div></div>
<section><h2>1. Freeze the intended behavior</h2><ul>''' + requirements + '''</ul><p class="note">Formula requirements are authoritative. Passing these checks does not prove that they capture all intended behavior. Human approval has not been granted.</p></section>
<section><h2>2. Diagnose the starting specification</h2><p>''' + _code(review["baseline_check"]["formula"]) + '''</p><p>''' + str(len(review["baseline_check"]["violations"])) + ''' violation records in the initial check.</p><details><summary>Inspect initial counterexamples</summary><pre>''' + failures + '''</pre></details></section>
<section><h2>3. Evolve with memory</h2><p class="muted">Retained candidates are checked again and count toward each round's budget.</p><div class="scroll"><table><thead><tr><th>Round</th><th>Evaluations</th><th>Retained formulas</th><th>Violations in best</th><th>AST nodes</th><th>Best candidate origin</th></tr></thead><tbody>''' + rounds + '''</tbody></table></div>''' + formulas + '''</section>
<section><h2>4. Inspect the selected candidate</h2><p>''' + _code(target["formula"]) + '''</p><p>''' + str(target["admitted_inputs"]) + ''' admitted inputs · ''' + str(target["permitted_pairs"]) + ''' permitted input/output pairs · ''' + str(len(target["violations"])) + ''' violation records.</p></section>
<section><h2>5. Review the behavior changes</h2><p class="muted">Green rows changed. Requirement-permitted outputs consider protected formulas; configured examples and determinism are checked separately.</p><div class="scroll"><table><thead><tr><th>Inputs</th><th>Starting spec permits</th><th>Selected spec permits</th><th>Requirements permit</th><th>Change</th></tr></thead><tbody>''' + decisions + '''</tbody></table></div>''' + omitted + '''</section>
<footer><p>''' + escape(review["scope"]) + ''' This review was generated after replaying every session round. No trading-performance or unbounded temporal claim is made.</p><p>Project: ''' + escape(review["project_digest"]) + '''<br>Session: ''' + escape(review["session_digest"]) + '''</p></footer></main></body></html>'''
