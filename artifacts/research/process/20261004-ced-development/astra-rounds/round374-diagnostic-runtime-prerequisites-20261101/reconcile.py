"""合并 R373/R374 的独立尝试，保留历史失败、未完成与新环境诊断结果。"""
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys

ROUND = Path(__file__).resolve().parent
ROOT = Path.cwd()
ORIGINAL = ROUND.parent / 'round373-full-workflow-rerun-20261101'
CONTINUATION = ROUND / 'continuation-v2'
COMPARISON = ROUND.parent / 'round375-diagnostic-database-scope-20261101'
OUTPUT = ROUND / 'reporting'
OUTPUT.mkdir(exist_ok=True)


def read(path):
    return json.loads(path.read_text()) if path.exists() else None


def path_ref(path):
    return str(path.relative_to(ROOT))


def pin(path):
    raw = path.read_bytes()
    return {'path': path_ref(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def event_state(events, launched, closed):
    reports = [e for e in events if e['event'] == 'report']
    failed = [e for e in reports if e['outcome'] == 'failed']
    if failed:
        return 'FAILED' if all(e['when'] == 'call' for e in failed) else 'ERROR'
    if any(e['event'] == 'deselected' for e in events):
        return 'DESELECTED'
    if any(e['outcome'] == 'skipped' for e in reports):
        return 'SKIPPED'
    if all(any(e['when'] == when and e['outcome'] == 'passed' for e in reports)
           for when in ('call', 'teardown')):
        return 'PASSED'
    if events:
        return 'INCOMPLETE'
    if launched:
        return 'NOT_STARTED_AFTER_STAGE_STOP' if closed else 'NOT_STARTED_YET'
    return 'NOT_RUN'


def main():
    final = sys.argv[1:] == ['--final']
    if sys.argv[1:] not in ([], ['--final']):
        raise SystemExit('Only --final is supported')
    if final and not (CONTINUATION / 'completion.json').exists():
        raise RuntimeError('Continuation has no terminal accounting receipt')
    comparison_result = COMPARISON / 'implementation/workbench_module_without_runtime_db/result.json'
    if final and not comparison_result.exists() and not (COMPARISON / 'not-run.json').exists():
        raise RuntimeError('R375 comparison has no terminal receipt')
    original_stages = read(ORIGINAL / 'stages.json')
    original_nodes = read(ORIGINAL / 'assignment-manifest.json')['stages']
    all_nodes = [n for ns in original_nodes.values() for n in ns]
    assert len(all_nodes) == len(set(all_nodes)) == 4732
    assignments = {n: s for s, ns in original_nodes.items() for n in ns}
    sources = []
    for s in original_stages:
        sources.append(('R373', s, ORIGINAL / 'implementation' / s['id']))
    for s in read(ROUND / 'stages.json'):
        sources.append(('R374', s, ROUND / 'implementation' / s['id']))
    remaining = read(CONTINUATION / 'planned-stages.json')
    ledger_path = CONTINUATION / 'budget-ledger.jsonl'
    budget_rows = [json.loads(line) for line in ledger_path.read_text().splitlines()] if ledger_path.exists() else []
    budget_by_stage = {r['stage_id']: r for r in budget_rows}
    for g in remaining['groups']:
        for s in g['children']:
            sources.append(('R374-continuation', s,
                            CONTINUATION / 'children' / s['id'] / 'implementation' / s['id']))
    comparison_plan = read(COMPARISON / 'plan.json')
    if comparison_plan:
        sources.append(('R375-comparison',
                        {'id': 'workbench_module_without_runtime_db',
                         'nodes': comparison_plan['command']['expected_nodeids_in_order']},
                        comparison_result.parent))
    evidence = []
    stages = []
    histories = defaultdict(list)
    failures = []
    for source, stage, directory in sources:
        result_path = directory / 'result.json'
        result = read(result_path)
        invocation_path = directory / 'invocation.json'
        invocation = read(invocation_path)
        interrupted = source == 'R373' and stage['id'] == 'pytest_software_05'
        closed = result is not None or interrupted
        events_path = directory / 'pytest-events.jsonl'
        by_node = defaultdict(list)
        parse_errors = []
        if events_path.exists():
            for i, line in enumerate(events_path.read_text().splitlines(), 1):
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as error:
                    parse_errors.append({'line': i, 'error': str(error)})
                    continue
                if 'nodeid' in event:
                    by_node[event['nodeid']].append(event)
        stage_counts = Counter()
        for node in stage.get('nodes', []):
            assert node in assignments, node
            events = by_node[node]
            state = event_state(events, invocation is not None, closed)
            reports = [e for e in events if e['event'] == 'report']
            record = {'source': source, 'stage_id': stage['id'], 'state': state,
                      'events_present': bool(events), 'launched': invocation is not None,
                      'stage_closed': closed,
                      'started_utc': invocation.get('started_utc') if invocation else None,
                      'evidence': path_ref(events_path) if events_path.exists() else None,
                      'call_duration_s': sum(e['duration'] for e in reports if e['when'] == 'call')}
            histories[node].append(record)
            stage_counts[state] += 1
            for report in reports:
                if report['outcome'] == 'failed':
                    failures.append({'nodeid': node, 'source': source, 'stage_id': stage['id'],
                                     'when': report['when'], 'longrepr': report['longrepr'],
                                     'evidence': path_ref(events_path)})
        for p in [invocation_path, result_path, events_path, directory / 'junit.xml']:
            if p.exists():
                evidence.append(pin(p))
        stages.append({'source': source, 'id': stage['id'], 'assigned_nodes': len(stage.get('nodes', [])),
                       'counts': dict(stage_counts), 'result': result,
                       'status': 'INTERRUPTED_FOR_ORCHESTRATION_RECOVERY' if interrupted else
                       (result.get('state') if result else ('RUNNING' if invocation else 'NOT_RUN')),
                       'budget_ledger': budget_by_stage.get(stage['id']) if source == 'R374-continuation' else None,
                       'event_parse_errors': parse_errors, 'directory': path_ref(directory)})
    nodes = []
    for node in all_nodes:
        attempts = histories[node]
        original = attempts[0]
        observed = [a for a in attempts if a['events_present']]
        latest = max(observed, key=lambda a: a['started_utc'] or '') if observed else None
        if latest:
            state = latest['state']
        elif any(a['launched'] and a['stage_closed'] for a in attempts):
            state = 'NOT_STARTED_AFTER_STAGE_STOP'
        else:
            state = 'NOT_RUN' if final else 'PENDING'
        nodes.append({'nodeid': node, 'original_stage': assignments[node], 'effective_state': state,
                      'original_state': original['state'],
                      'historical_failure': any(a['state'] in ('FAILED', 'ERROR') for a in attempts),
                      'historical_incomplete': any(a['state'] == 'INCOMPLETE' for a in attempts),
                      'diagnostic_recovered': bool(latest and latest['state'] == 'PASSED' and
                          any(a['state'] in ('FAILED', 'ERROR', 'INCOMPLETE') for a in attempts)),
                      'attempts': attempts})
    summary = {'schema': 'bigsmall.r373-r375.coverage.v2', 'final': final,
               'generated_utc': datetime.now(UTC).isoformat(), 'collected_unique': 4732,
               'continuation_manifest': path_ref(CONTINUATION / 'planned-stages.json'),
               'effective_counts': dict(Counter(n['effective_state'] for n in nodes)),
               'original_counts': dict(Counter(n['original_state'] for n in nodes)),
               'historically_failed_unique': sum(n['historical_failure'] for n in nodes),
               'historically_incomplete_unique': sum(n['historical_incomplete'] for n in nodes),
               'diagnostic_recovered_unique': sum(n['diagnostic_recovered'] for n in nodes),
               'stages': stages,
               'limits': ['Current dirty workspace, including uncommitted local_temporal candidate, was tested.',
                          'Original failures and timeouts remain separate evidence.',
                          'UTC diagnostic 3600s caps do not replace original combined600s acceptance.',
                          'No real model/hardware execution or formal research acceptance.']}
    suffix = '' if final else '-live'
    values = {f'summary{suffix}.json': summary,
              f'coverage-manifest{suffix}.json': {'summary': summary, 'nodes': nodes},
              f'failures{suffix}.json': failures,
              f'evidence-manifest{suffix}.json': evidence}
    for name, value in values.items():
        path = OUTPUT / name
        if final and path.exists():
            raise RuntimeError('Refusing to replace final report: ' + str(path))
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('stages', 'limits')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
