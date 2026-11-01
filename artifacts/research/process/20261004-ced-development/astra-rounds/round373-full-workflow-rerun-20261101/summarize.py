"""Reconcile original per-node events, including interrupted and excluded nodes."""
from collections import Counter, defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
stages = json.loads((ROOT / 'stages.json').read_text())
coverage = []
stage_summaries = []
for stage in stages:
    directory = ROOT / 'implementation' / stage['id']
    retry = directory.with_name(directory.name + '-environment-retry')
    if retry.exists():
        directory = retry
    result_path = directory / 'result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    events_path = directory / 'pytest-events.jsonl'
    events = []
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    by_node = defaultdict(list)
    for event in events:
        if 'nodeid' in event:
            by_node[event['nodeid']].append(event)
    outcomes = Counter()
    for node in stage.get('nodes', []):
        node_events = by_node[node]
        reports = [e for e in node_events if e['event'] == 'report']
        failures = [e for e in reports if e['outcome'] == 'failed']
        if failures:
            state = 'FAILED' if all(e['when'] == 'call' for e in failures) else 'ERROR'
        elif any(e['event'] == 'deselected' for e in node_events):
            state = 'DESELECTED'
        elif any(e['outcome'] == 'skipped' for e in reports):
            state = 'SKIPPED'
        elif any(e['when'] == 'call' and e['outcome'] == 'passed' for e in reports) and any(e['when'] == 'teardown' and e['outcome'] == 'passed' for e in reports):
            state = 'PASSED'
        elif node_events:
            state = 'INCOMPLETE'
        else:
            state = 'NOT_COMPLETED' if result else 'PENDING'
        outcomes[state] += 1
        coverage.append({'nodeid': node, 'stage_id': stage['id'], 'state': state,
                         'evidence': str(events_path.relative_to(ROOT)),
                         'failures': failures,
                         'call_duration_s': sum(e['duration'] for e in reports if e['when'] == 'call')})
    stage_summaries.append({'id': stage['id'], 'result': result, 'counts': dict(outcomes)})
totals = Counter(row['state'] for row in coverage)
assert len(coverage) == len({row['nodeid'] for row in coverage}) == 4732
summary = {'collected': 4732, 'counts': dict(totals), 'stages': stage_summaries}
(ROOT / 'coverage-manifest.json').write_text(json.dumps({'summary': summary, 'nodes': coverage}, ensure_ascii=False, indent=2) + '\n')
(ROOT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'counts': dict(totals), 'finished_stages': sum(s['result'] is not None for s in stage_summaries),
                  'active': [s['id'] for s in stage_summaries if s['result'] is None and (ROOT/'implementation'/s['id']).exists()]}, ensure_ascii=False))
