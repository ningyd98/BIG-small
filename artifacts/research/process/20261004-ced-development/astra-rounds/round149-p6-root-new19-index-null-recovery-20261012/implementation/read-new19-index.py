from pathlib import Path
from collections import Counter
import hashlib
import json
import os
import stat
import xml.etree.ElementTree as ET

ROOT = Path('/home/ningyd/文档/ChatGPT/BIGsmall')
BASE = ROOT / 'artifacts/research/process/20261004-ced-development/astra-rounds'
ROUND = BASE / 'round149-p6-root-new19-index-null-recovery-20261012'
R147 = BASE / 'round147-p6-foreign-repository-fixture-lock-recovery-20261012'
PLAN_SHA = 'b025922cfa547dd8eb9166ff5f01132e2817fdf0a1bcc3d4ad3cdba24adfada3'
checks = []


def record(path):
    assert isinstance(path, (str, Path)) and str(path)
    path = Path(path)
    assert path.is_absolute() and stat.S_ISREG(path.lstat().st_mode)
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def check(name, value, detail=None):
    checks.append({'check': name, 'match': bool(value), 'detail': detail})


def verify(pin, field='path'):
    assert isinstance(pin, dict) and isinstance(pin.get('bytes'), int)
    assert isinstance(pin.get('sha256'), str) and len(pin['sha256']) == 64
    actual = record(pin[field])
    check(field + ' bytes/hash', actual['bytes'] == pin['bytes'] and actual['sha256'] == pin['sha256'], actual)
    return actual


def load(path):
    return json.loads(Path(path).read_bytes())


plan_path = ROUND / 'plan.json'
assert record(plan_path)['sha256'] == PLAN_SHA
plan = load(plan_path)
input_pins = {x['path']: x for x in plan['inputs']}
assert len(input_pins) == len(plan['inputs']) == 10
for pin in plan['inputs']:
    verify(pin)
index_path = R147 / 'implementation/new19-freeze/source-index.json'
index = load(index_path)
schema = plan['schema_observations']
assert isinstance(index['files'], list) and len(index['files']) == 1208
assert dict(Counter(x['group'] for x in index['files'])) == schema['groups']
sole_null = schema['null_source_records'][0]
null_count = 0
primary = {}
for entry in index['files']:
    verify(entry, 'snapshot')
    assert entry['snapshot'] not in primary
    primary[entry['snapshot']] = entry
    source = entry.get('source')
    if source is None:
        assert all(entry.get(k) == sole_null[k] for k in ['group', 'source', 'snapshot', 'bytes', 'sha256'])
        null_count += 1
        check('source_not_applicable_generated_report_snapshot_verified', True, entry)
    else:
        assert isinstance(source, str) and source
        verify(entry, 'source')
assert null_count == 1


def subset(entries, expected_count, group):
    assert isinstance(entries, list) and len(entries) == expected_count
    for entry in entries:
        assert entry['group'] == group and primary.get(entry['snapshot']) == entry
    check('typed primary subset ' + group, True, expected_count)


subset(index['sources'], 6, 'current_source')
subset(index['raw'], 5, 'actual_command_raw')
subset(index['fixture'], 1192, 'actual_fixture_regular')
assert isinstance(index['ledgers'], dict) and len(index['ledgers']) == 4
subset([x['file'] for x in index['ledgers'].values()], 4, 'actual_ledger_snapshot')
assert len(index['protected']) == 53 and len(index['references']) == 9
for entry in index['protected'] + index['references']:
    verify(entry)
assert len(index['symlink_metadata']) == 7
for entry in index['symlink_metadata']:
    path = Path(entry['path'])
    info = path.lstat()
    check('symlink metadata nofollow', stat.S_ISLNK(info.st_mode) and os.readlink(path) == entry['target'] and info.st_mode == entry['mode'] and info.st_size == entry['size'] and info.st_mtime_ns == entry['mtime_ns'], entry)

original_plan = load(R147 / 'plan.json')
command = original_plan['inherited_new_green19']
result_entries = [x for x in index['raw'] if Path(x['source']).name == 'result.json']
assert len(result_entries) == 1
result = load(result_entries[0]['snapshot'])
for field in ['argv', 'cwd', 'env', 'evidence_dir']:
    check('new19 exact ' + field, result[field] == command[field])
check('actual new19 spent1/0 exit0', result['used'] == 1 and result['remaining'] == 0 and result['exit_code'] == 0)
for name, pin in result['raw_outputs'].items():
    entries = [x for x in index['raw'] if Path(x['source']).name == name]
    assert len(entries) == 1
    check('actual stream recorded pin ' + name, entries[0]['bytes'] == pin['bytes'] and entries[0]['sha256'] == pin['sha256'])

assert len(index['runs']) == 4
mapping = {}
run_summaries = []
expected_counts = [(20, 19, 1), (1, 1, 0), (19, 19, 0), (1, 1, 0)]
for run, counts in zip(index['runs'], expected_counts):
    verify(run['junit'])
    tree = ET.parse(run['junit']['path'])
    suites = list(tree.iter('testsuite'))
    cases = list(tree.iter('testcase'))
    assert len(suites) == 1
    passed, failed = set(), set()
    for case in cases:
        node = 'tests/test_operational_runtime_closure.py::' + case.get('name')
        bad = any(child.tag in {'failure', 'error', 'skipped'} for child in case)
        assert node not in passed and node not in failed
        (failed if bad else passed).add(node)
    suite = suites[0].attrib
    check('actual JUnit counts ' + run['run'], len(cases) == counts[0] and len(passed) == counts[1] and len(failed) == counts[2] and suite['tests'] == str(counts[0]) and suite['failures'] == str(counts[2]) and suite['errors'] == '0' and suite['skipped'] == '0')
    check('actual JUnit recorded exact nodes ' + run['run'], passed == set(run['passed_nodes']) and failed == set(run['failed_or_nonpass_nodes']))
    if run['run'] == 'original_new19_19pass':
        expected = {x for x in command['argv'] if x.startswith('tests/')}
        check('new19 exact19 unique nodes', len(expected) == 19 and passed == expected and not failed)
    for node in sorted(passed):
        mapping.setdefault(node, []).append(run['run'])
    run_summaries.append({'run': run['run'], 'passed': sorted(passed), 'failed': sorted(failed), 'junit': run['junit']})
proof_pins = [x for x in index['references'] if x['path'] == str(R147 / 'implementation/delta_proof/proof.json')]
assert len(proof_pins) == 1
proof = load(proof_pins[0]['path'])
check('exact source scope proof', proof['status'] == 'PASS_FOREIGN_FIXTURE_DELTA_SOURCE_ONLY' and proof['other39_nodes_and_three_other_variants_unchanged'] and proof['entire_module_AST_type_comments_equal_after_only_exact_statement_normalization'])
verify(proof['after'])
verify(proof['prior_type_proof'])
check('40unique pass mapping exact', len(mapping) == index['unique_terminal_pass_nodes'] == 40 and mapping == index['terminal_pass_evidence_mapping'] and set(mapping) == set(proof['parameter_values_ids_and40_source_nodeids_unchanged']))

subset(index['lifecycle_files'], 18, 'actual_fixture_regular')
lifecycle = []
for entry in index['lifecycle_files']:
    data = load(entry['snapshot'])
    check('actual lifecycle session closed', data['session_closed'], entry['source'])
    check('actual lifecycle raw_exit1/shutdown1', data['calls'].count('raw_exit') == 1 and data['calls'].count('shutdown') == 1, entry['source'])
    lifecycle.append({'source': entry['source'], 'snapshot': entry['snapshot'], 'calls': data['calls'], 'session_closed': data['session_closed']})
output = ROUND / 'implementation/reader.json'
receipt = {'status': 'PASS_SCHEMA_AWARE_NEW19_METADATA' if all(x['match'] for x in checks) else 'STOP_MISMATCH', 'authority': record(index_path), 'checks': checks, 'file_snapshots': 1208, 'present_sources': 1207, 'source_not_applicable': sole_null, 'fixture_regular': 1192, 'symlink_metadata': 7, 'actual_runs': run_summaries, 'terminal_pass_mapping': mapping, 'unique_terminal_pass_nodes': 40, 'single40_run': False, 'actual_lifecycle': lifecycle, 'product_executions': 0, 'old_reader_replay': 0, 'acceptance': False, 'boundary': 'CPU software evidence only. Fresh independent final review still required; no B/C/D/native/physical/actual/formal acceptance.'}
with output.open('x') as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(json.dumps({'status': receipt['status'], 'receipt': record(output), 'checks': len(checks), 'mismatches': sum(not x['match'] for x in checks), 'unique_terminal_pass_nodes': 40}, ensure_ascii=False))
if receipt['status'] != 'PASS_SCHEMA_AWARE_NEW19_METADATA':
    raise SystemExit(1)
