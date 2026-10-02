"""Reproduce the exit-policy workflow; no neural model or API key is invoked."""

import argparse
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zeno_speccheck.cli import source_digest
from zeno_speccheck.logic import parse
from zeno_speccheck.model import digest, load_project, read_json
from zeno_speccheck.review import render_html, review_session
from zeno_speccheck.session import evolve_session, replay_session, session_feedback
from zeno_speccheck.tau import TauConfig, check_tau, export_tau


SIMPLIFICATION = '(sell <-> (holding && (profit || exit))) && (hold_next <-> (holding && !sell))'


def verify_independently(formula):
    candidate = parse(formula)
    for holding, profit, exit_signal, sell, next_hold in product((False, True), repeat=5):
        expected_sell = holding and (profit or exit_signal)
        expected_hold = holding and not expected_sell
        values = dict(holding=holding, profit=profit, exit=exit_signal, sell=sell, hold_next=next_hold)
        if candidate.evaluate(values) != (sell == expected_sell and next_hold == expected_hold):
            raise AssertionError(f'Independent transition oracle disagrees at {values}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='runs/exit-demo')
    parser.add_argument('--tau-python')
    parser.add_argument('--tau-module-dir')
    parser.add_argument('--tau-source-revision')
    args = parser.parse_args()
    destination = Path(args.out)
    destination.mkdir(parents=True, exist_ok=True)
    project_raw = read_json(ROOT / 'examples/deflationary_exit.json')
    project = load_project(project_raw)
    source = source_digest()
    def save(name, value, *, compact=False):
        options = {'separators': (',', ':')} if compact else {'indent': 2}
        (destination / name).write_text(json.dumps(value, sort_keys=True, **options) + '\n', encoding='utf-8')
    first = evolve_session(project, source, seed=0, max_evaluations=64)
    save('round-1-feedback.json', session_feedback(project, first, source))
    second = evolve_session(project, source, previous=first, seed=1, max_evaluations=128)
    save('round-2-feedback.json', session_feedback(project, second, source))
    if second['best_candidate'] is None:
        raise AssertionError('The deterministic two-round demo did not find a repair')
    verify_independently(second['best_candidate']['check']['formula'])
    # The first two rounds receive no hand-written correct candidate. Only after
    # repair, replay this assistant-authored simplification as an external proposal.
    offered = {'schema':'zeno/proposals/v1', 'project_digest':project.identity,
               'proposals':[{'formula':SIMPLIFICATION,
                             'rationale':'The evolved (!profit -> exit) equals (profit || exit); use the simpler expression.'}]}
    final = evolve_session(project, source, previous=second, seed=2, generations=0,
                           max_evaluations=16, proposal_data=offered)
    verify_independently(final['best_candidate']['check']['formula'])
    replay = replay_session(project, final, source)
    if replay['status'] != 'pass':
        raise AssertionError('Demo session replay failed')
    review = review_session(project, final, source)
    save('proposals.json', offered)
    save('session.json', final, compact=True)
    save('replay.json', replay)
    (destination / 'review.html').write_text(render_html(review), encoding='utf-8')
    summary = {'schema':'zeno/exit-demo/v1', 'source_digest':source,
               'project_digest':project.identity, 'session_digest':digest(final),
               'rounds':review['progress'], 'evaluated_candidates':final['evaluated_candidates'],
               'unique_candidates':final['unique_candidates'], 'retained_witnesses':len(final['counterexamples']),
               'changed_inputs':[row for row in review['decision_rows'] if row['changed']],
               'winner':final['best_candidate']['check'], 'independent_transition_oracle':'all 32 assignments agree',
               'proposal_provenance':'Round 3 replays an assistant-authored simplification fixture; no model is invoked by this script.',
               'approval':'not_granted', 'benchmark_claim':'No superiority claim; one illustrative task with fixed seeds.'}
    if args.tau_python:
        config = TauConfig(args.tau_python, args.tau_module_dir, 15, args.tau_source_revision)
        expr = parse(final['best_candidate']['check']['formula'], project.variables)
        exported = export_tau(project, expr, 'sbf')
        native = check_tau(exported['formula'], exported['requirements'], config)
        save('tau-crosscheck.json', {'translation':exported, 'check':native})
        summary['tau_status'] = native['status']
    else:
        summary['tau_status'] = 'not_run'
    save('summary.json', summary)
    print(json.dumps({'out':str(destination), 'rounds':[(r['evaluated_candidates'],r['remaining_violations']) for r in review['progress']],
                      'replay':replay['status'], 'tau':summary['tau_status']}))
    return 0 if summary['tau_status'] in ('pass','not_run') else 2


if __name__ == '__main__':
    raise SystemExit(main())
